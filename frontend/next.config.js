/** @type {import('next').NextConfig} */

// Frontend port and host: used for loop guard detection
const frontendPort = process.env.PORT || process.env.FRONTEND_PORT || "3000";
const frontendHost = process.env.FRONTEND_HOST || "127.0.0.1";

// Backend port and host: ONE single source of truth for backend targeting.
// CRITICAL: NEVER fall back to process.env.PORT because PORT is the frontend's own listening port.
const backendHost = process.env.BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.BACKEND_PORT || "8000";
const defaultBackendUrl = `http://${backendHost}:${backendPort}`;

const resolvedBackendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  defaultBackendUrl;

const healthPath = process.env.NEXT_PUBLIC_HEALTH_PATH || process.env.HEALTH_PATH || "/health";

// Loop guard: compare resolved backend URL against frontend host & port
function isLoopback(backendUrlStr, feHost, fePort) {
  try {
    const parsed = new URL(backendUrlStr);
    const bPort = parsed.port || (parsed.protocol === "https:" ? "443" : "80");
    const fPort = String(fePort || "3000");

    if (bPort !== fPort) {
      return false;
    }

    const isLocal = (h) =>
      !h ||
      h === "localhost" ||
      h === "127.0.0.1" ||
      h === "0.0.0.0" ||
      h === "::1" ||
      h === "[::1]";

    const bHost = parsed.hostname.toLowerCase();
    const fHost = (feHost || "127.0.0.1").toLowerCase();

    if (isLocal(bHost) && isLocal(fHost)) {
      return true;
    }

    return bHost === fHost;
  } catch {
    return false;
  }
}

if (isLoopback(resolvedBackendUrl, frontendHost, frontendPort)) {
  const errorMsg = `BACKEND_URL points to the frontend itself: ${resolvedBackendUrl}`;
  console.error(`\n❌ [LOOP GUARD ERROR] ${errorMsg}`);
  console.error(
    `   Frontend is running on port ${frontendPort}, but backend target resolved to ${resolvedBackendUrl}.`
  );
  console.error(
    `   To fix this, set BACKEND_PORT (e.g. 8000) or BACKEND_URL (e.g. http://127.0.0.1:8000) to point to your FastAPI backend.\n`
  );
  throw new Error(errorMsg);
}

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: resolvedBackendUrl,
    NEXT_PUBLIC_API_BASE_URL: resolvedBackendUrl,
    NEXT_PUBLIC_BACKEND_URL: resolvedBackendUrl,
    NEXT_PUBLIC_FRONTEND_PORT: frontendPort,
    NEXT_PUBLIC_HEALTH_PATH: healthPath,
    NEXT_PUBLIC_HEALTH_POLL_INTERVAL_MS: process.env.NEXT_PUBLIC_HEALTH_POLL_INTERVAL_MS || "10000",
    NEXT_PUBLIC_HEALTH_TIMEOUT_MS: process.env.NEXT_PUBLIC_HEALTH_TIMEOUT_MS || "3500",
    NEXT_PUBLIC_HEALTH_MAX_RETRIES: process.env.NEXT_PUBLIC_HEALTH_MAX_RETRIES || "5",
    NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_MS: process.env.NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_MS || "1000",
    NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_FACTOR: process.env.NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_FACTOR || "1.5",
  },

  // Proxy /api/* and /health* requests through Next.js to the backend.
  // This prevents the browser from connecting to the backend directly,
  // eliminating CORS preflight failures and IPv4/IPv6 resolution mismatches.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${resolvedBackendUrl}/api/:path*`,
      },
      {
        source: healthPath,
        destination: `${resolvedBackendUrl}${healthPath}`,
      },
      ...(healthPath !== "/health/ready"
        ? [
            {
              source: "/health/ready",
              destination: `${resolvedBackendUrl}/health/ready`,
            },
          ]
        : []),
    ];
  },
};

module.exports = nextConfig;

