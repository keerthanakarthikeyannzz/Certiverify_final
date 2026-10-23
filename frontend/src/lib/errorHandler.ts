import { AxiosError } from "axios";
import { BACKEND_URL, isBackendLoopingToFrontend } from "./api";

/**
 * Checks whether an error is due to inability to connect to the backend:
 * - Refusal by loop guard (BACKEND_URL points to frontend itself)
 * - Network errors / connection refused / DNS failure
 * - Client timeout (ECONNABORTED)
 * - Proxy 502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout
 * - Proxy 500 error without an application JSON detail payload (Next.js ETIMEDOUT / ECONNREFUSED)
 */
export function isBackendUnreachableError(err: unknown): boolean {
  if (!err) return false;

  if (err instanceof Error && err.message.includes("BACKEND_URL points to the frontend itself")) {
    return true;
  }

  const axErr = err as AxiosError<{ detail?: unknown; message?: string }>;

  // No response at all (client-side timeout, ECONNREFUSED, ERR_NETWORK)
  if (!axErr.response) {
    return true;
  }

  const status = axErr.response.status;

  // Standard proxy / gateway failure statuses
  if (status === 502 || status === 503 || status === 504) {
    return true;
  }

  // Next.js dev server proxy returns 500 with plain text or HTML when target fails connect ETIMEDOUT
  if (status === 500) {
    const data = axErr.response.data;
    if (!data) return true;
    if (typeof data === "string") return true;
    if (typeof data === "object" && !("detail" in data)) return true;
  }

  return false;
}

export function getUnreachableBackendMessage(url: string = BACKEND_URL): string {
  if (isBackendLoopingToFrontend(url)) {
    return `Can't reach the verification server. Configuration error: BACKEND_URL points to the frontend itself (${url}). Please configure BACKEND_PORT or BACKEND_URL to your backend server (e.g. port 8000).`;
  }
  return `Can't reach the verification server. Make sure the backend is running (${url})`;
}

/**
 * Formats API errors for user display:
 * - Surfaces specific connection error message if backend is unreachable.
 * - Preserves server's own detail message for 400, 401, 409, 422, and genuine 500.
 */
export function formatErrorMessage(
  err: unknown,
  fallbackMessage: string = "Request failed. Please try again."
): string {
  if (!err) return fallbackMessage;

  if (isBackendUnreachableError(err)) {
    return getUnreachableBackendMessage();
  }

  const axErr = err as AxiosError<{ detail?: unknown; message?: string }>;
  const detail = axErr.response?.data?.detail;

  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail.map((item: any) => {
      const msg = item?.msg || "Validation error";
      const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null;
      const cleanMsg = msg.replace(/^Value error,\s*/i, "");
      return field && typeof field === "string" && !cleanMsg.toLowerCase().includes(field.toLowerCase())
        ? `${field}: ${cleanMsg}`
        : cleanMsg;
    });
    return messages.join(". ");
  }

  if (axErr.response?.data?.message) {
    return axErr.response.data.message;
  }

  if (axErr.response?.status === 409) {
    return "An account with this email already exists.";
  }

  if (axErr.response?.status === 401) {
    return "Authentication failed. Please check your credentials.";
  }

  return axErr.message || fallbackMessage;
}
