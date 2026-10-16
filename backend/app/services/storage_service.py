"""
Storage abstraction layer.
Switch backends purely via STORAGE_BACKEND env var — nothing else in the
codebase needs to change. Module 2 uses this for certificate file storage.
"""
import hashlib
import os
import uuid
from abc import ABC, abstractmethod

import aiofiles
from fastapi import UploadFile

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subdir: str = "certificates") -> tuple[str, int, str]:
        """Returns (storage_path_or_url, size_bytes, sha256_hash)."""

    @abstractmethod
    async def save_bytes(self, data: bytes, filename: str, subdir: str = "generated") -> str:
        """Saves raw bytes (e.g. a generated ELA heatmap or PDF report) and returns the storage path/URL."""

    @abstractmethod
    async def read(self, storage_path: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        ...


class LocalStorageBackend(StorageBackend):
    def __init__(self):
        self.base_dir = os.path.abspath(settings.UPLOAD_DIR)
        os.makedirs(self.base_dir, exist_ok=True)

    def _verify_safe_path(self, path: str) -> str:
        """Enforces path traversal safety — guarantees path remains within UPLOAD_DIR."""
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(self.base_dir):
            raise ValueError(f"Access denied: Path '{path}' escapes configured storage root.")
        return abs_path

    async def save(self, file: UploadFile, subdir: str = "certificates") -> tuple[str, int, str]:
        # Clean subdir to prevent directory traversal in path construction
        clean_subdir = os.path.normpath(subdir).lstrip("/\\.").replace("..", "")
        target_dir = self._verify_safe_path(os.path.join(self.base_dir, clean_subdir))
        os.makedirs(target_dir, exist_ok=True)

        ext = os.path.splitext(file.filename or "")[1].lower()
        unique_name = f"{uuid.uuid4()}{ext}"
        full_path = os.path.join(target_dir, unique_name)

        sha256 = hashlib.sha256()
        size = 0
        async with aiofiles.open(full_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                sha256.update(chunk)
                size += len(chunk)
                await out.write(chunk)
        await file.seek(0)

        return full_path, size, sha256.hexdigest()

    async def read(self, storage_path: str) -> bytes:
        safe_path = self._verify_safe_path(storage_path)
        async with aiofiles.open(safe_path, "rb") as f:
            return await f.read()

    async def save_bytes(self, data: bytes, filename: str, subdir: str = "generated") -> str:
        clean_subdir = os.path.normpath(subdir).lstrip("/\\.").replace("..", "")
        target_dir = self._verify_safe_path(os.path.join(self.base_dir, clean_subdir))
        os.makedirs(target_dir, exist_ok=True)
        safe_filename = os.path.basename(filename)
        full_path = self._verify_safe_path(os.path.join(target_dir, safe_filename))
        async with aiofiles.open(full_path, "wb") as out:
            await out.write(data)
        return full_path

    async def delete(self, storage_path: str) -> None:
        safe_path = self._verify_safe_path(storage_path)
        if os.path.exists(safe_path):
            os.remove(safe_path)


class S3StorageBackend(StorageBackend):
    """AWS S3-backed storage. Requires boto3 + AWS credentials in settings."""

    def __init__(self):
        import boto3
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.AWS_S3_BUCKET

    async def save(self, file: UploadFile, subdir: str = "certificates") -> tuple[str, int, str]:
        ext = os.path.splitext(file.filename or "")[1].lower()
        key = f"{subdir.strip('/')}/{uuid.uuid4()}{ext}"

        contents = await file.read()
        sha256 = hashlib.sha256(contents).hexdigest()
        size = len(contents)

        # Private object access + Server-Side Encryption
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=contents,
            ContentType=file.content_type,
            ServerSideEncryption="AES256",
        )
        await file.seek(0)
        return f"s3://{self.bucket}/{key}", size, sha256

    async def read(self, storage_path: str) -> bytes:
        key = storage_path.split(f"s3://{self.bucket}/")[-1]
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    async def save_bytes(self, data: bytes, filename: str, subdir: str = "generated") -> str:
        key = f"{subdir.strip('/')}/{os.path.basename(filename)}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self.bucket}/{key}"

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        key = storage_path.split(f"s3://{self.bucket}/")[-1]
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def delete(self, storage_path: str) -> None:
        key = storage_path.split(f"s3://{self.bucket}/")[-1]
        self.client.delete_object(Bucket=self.bucket, Key=key)


class CloudinaryStorageBackend(StorageBackend):
    """Cloudinary-backed storage — good fit for certificate images/PDF previews."""

    def __init__(self):
        import cloudinary
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )

    async def save(self, file: UploadFile, subdir: str = "certificates") -> tuple[str, int, str]:
        import cloudinary.uploader
        contents = await file.read()
        sha256 = hashlib.sha256(contents).hexdigest()
        size = len(contents)

        result = cloudinary.uploader.upload(
            contents, folder=subdir, resource_type="auto", public_id=str(uuid.uuid4()),
        )
        await file.seek(0)
        return result["secure_url"], size, sha256

    async def read(self, storage_path: str) -> bytes:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(storage_path)
            return resp.content

    async def save_bytes(self, data: bytes, filename: str, subdir: str = "generated") -> str:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            data, folder=subdir, resource_type="image", public_id=os.path.splitext(filename)[0],
        )
        return result["secure_url"]

    async def delete(self, storage_path: str) -> None:
        import cloudinary.uploader
        public_id = storage_path.split("/")[-1].split(".")[0]
        cloudinary.uploader.destroy(public_id)


def get_storage_backend() -> StorageBackend:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "s3":
        return S3StorageBackend()
    if backend == "cloudinary":
        return CloudinaryStorageBackend()
    return LocalStorageBackend()
