// Default to a relative base so the browser calls the frontend origin and the
// Next rewrite proxies to the backend — this keeps the session cookie first-party.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Turn a backend-relative file URL (e.g. "/storage/x.svg") into an absolute one. */
export function assetUrl(fileUrl: string | null): string | null {
  if (!fileUrl) return null;
  return fileUrl.startsWith("http") ? fileUrl : `${API_BASE}${fileUrl}`;
}

// Local "acting as" family user (attribution only — not authentication).
const ACTIVE_USER_KEY = "scs_active_user_id";
const ACTIVE_USER_HEADER = "X-SCS-Family-User-Id";

export function getActiveUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_USER_KEY);
}

export function setActiveUserId(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(ACTIVE_USER_KEY, id);
  else window.localStorage.removeItem(ACTIVE_USER_KEY);
}

function activeUserHeaders(): Record<string, string> {
  const id = getActiveUserId();
  return id ? { [ACTIVE_USER_HEADER]: id } : {};
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...init,
    // Headers last so the active-user header is never clobbered by `init`.
    headers: {
      "Content-Type": "application/json",
      ...activeUserHeaders(),
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function formRequest<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body,
    cache: "no-store",
    credentials: "include",
    headers: activeUserHeaders(),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const payload = await res.json();
      if (payload?.detail) detail = payload.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}



export async function downloadZip(path: string, input: unknown, filename: string) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
