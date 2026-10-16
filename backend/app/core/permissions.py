import enum

class Permission(str, enum.Enum):
    CERTIFICATE_UPLOAD = "certificate:upload"
    CERTIFICATE_READ = "certificate:read"
    CERTIFICATE_VERIFY = "certificate:verify"
    CERTIFICATE_DELETE = "certificate:delete"
    ORG_MANAGE = "org:manage"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"
    API_KEY_WRITE = "api_key:write"

PERMISSIONS_MAP: dict[str, list[str]] = {
    "admin": [
        "certificate:upload", "certificate:read", "certificate:verify", "certificate:delete",
        "org:manage", "user:manage", "audit:read", "api_key:write"
    ],
    "owner": [
        "certificate:upload", "certificate:read", "certificate:verify", "certificate:delete",
        "org:manage", "user:manage", "audit:read", "api_key:write"
    ],
    "university": [
        "certificate:upload", "certificate:read", "certificate:verify", "certificate:delete",
        "org:manage", "user:manage", "audit:read", "api_key:write"
    ],
    "employer": [
        "certificate:read", "certificate:verify"
    ],
    "student": [
        "certificate:upload", "certificate:read", "certificate:verify"
    ],
    "member": [
        "certificate:upload", "certificate:read", "certificate:verify"
    ],
    "viewer": [
        "certificate:read"
    ]
}

def has_permission(role: str, permission: str) -> bool:
    role_str = str(role).lower()
    allowed = PERMISSIONS_MAP.get(role_str, [])
    return permission in allowed or "admin" in role_str or "owner" in role_str
