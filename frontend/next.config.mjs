/** @type {import('next').NextConfig} */
// Build-directory isolation so a dev server can never corrupt the production
// build: production (`next build` / `next start`, NODE_ENV=production) writes to
// `.next`; dev (`next dev`, NODE_ENV=development) writes to `.next-dev`. An
// explicit NEXT_DIST_DIR env var overrides either. Because Next sets NODE_ENV
// automatically, `next dev` cannot touch `.next` no matter how it is launched.
const distDir =
  process.env.NEXT_DIST_DIR ||
  (process.env.NODE_ENV === "development" ? ".next-dev" : ".next");

// Proxy API + storage to the backend so the browser talks to the frontend
// origin only. This keeps the session cookie first-party (HTTP-only, SameSite=Lax
// works without cross-origin/Secure friction on localhost). Override the backend
// target with BACKEND_ORIGIN if needed.
const backendOrigin = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8002";

const nextConfig = {
  reactStrictMode: true,
  distDir,
  // Cloned-voice synthesis (VibeVoice) runs inside one request and can take
  // minutes; Next's 30 s proxy default would cut it off. Matches the backend's
  // VIBEVOICE_TIMEOUT_SECONDS.
  experimental: { proxyTimeout: 30 * 60 * 1000 },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
      { source: "/storage/:path*", destination: `${backendOrigin}/storage/:path*` },
    ];
  },
};

export default nextConfig;
