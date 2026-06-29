// Routes that render a clean, logged-out auth layout (no sidebar nav, no topbar
// greeting): login, signup, and first-time admin password setup.
const AUTH_ROUTE_PREFIXES = ["/login", "/signup", "/setup"];

export function isAuthRoute(pathname: string | null): boolean {
  if (!pathname) return false;
  return AUTH_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}
