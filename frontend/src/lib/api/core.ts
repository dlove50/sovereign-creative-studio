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

/** An API failure with the HTTP status attached (0 = the studio could not be reached). */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const UNREACHABLE = "Can't reach the studio. Check that it is running, then try again.";

/** Turn FastAPI's error body into text a person can read (detail may be a string, a list of field errors, or an object). */
export function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const entry = item as { loc?: unknown[]; msg?: unknown; message?: unknown };
          const text = typeof entry.msg === "string" ? entry.msg : typeof entry.message === "string" ? entry.message : "";
          const where = Array.isArray(entry.loc) ? entry.loc.filter((x) => x !== "body" && x !== "query").join(" > ") : "";
          return text ? (where ? `${where}: ${text}` : text) : "";
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

/** Read a failed response into an ApiError with a readable message. */
export async function readError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(describeDetail(detail, res.statusText || `Request failed (${res.status})`), res.status);
}

/** fetch that sends the session cookie and the acting-as header, and turns a network failure into a plain message. */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: { ...activeUserHeaders(), ...(init?.headers as Record<string, string> | undefined) },
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedFetch(path, {
    ...init,
    // Headers last so the active-user header is never clobbered by `init`.
    headers: { "Content-Type": "application/json", ...(init?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) throw await readError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** DELETE (or any call with no response body to read). Throws a readable ApiError when the server refuses. */
export async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const res = await authedFetch(path, init);
  if (!res.ok) throw await readError(res);
}

export async function formRequest<T>(path: string, body: FormData): Promise<T> {
  const res = await authedFetch(path, { method: "POST", body });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<T>;
}

/** Save a blob as a file download. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadZip(path: string, input: unknown, filename: string) {
  const res = await authedFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await readError(res);
  saveBlob(await res.blob(), filename);
}
