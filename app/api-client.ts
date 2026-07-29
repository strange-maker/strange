function normalizeApiBase(value: string) {
  return value
    .trim()
    .replace(/^["']|["']$/g, "")
    .replace(/\/+$/, "");
}

export const API_BASE = normalizeApiBase(
  process.env.NEXT_PUBLIC_API_BASE_URL || "",
);
export const API_BASE_VALID = /^https?:\/\/[^/]+/i.test(API_BASE);

export type SessionUser = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "analyst" | "sales" | "viewer";
  is_active: boolean;
};
type Tokens = {
  access_token: string;
  refresh_token: string;
  user: SessionUser;
};

const ACCESS = "sales-intel-access";
const REFRESH = "sales-intel-refresh";
const API_TIMEOUT_MS = 15_000;
export const AUTH_EXPIRED_EVENT = "sales-intel-auth-expired";

const memorySession = new Map<string, string>();
let refreshInFlight: Promise<boolean> | null = null;

function readSession(key: string) {
  if (typeof window === "undefined") return memorySession.get(key) ?? null;
  try {
    return globalThis.sessionStorage.getItem(key) ?? memorySession.get(key) ?? null;
  } catch {
    return memorySession.get(key) ?? null;
  }
}

function writeSession(key: string, value: string) {
  memorySession.set(key, value);
  if (typeof window === "undefined") return;
  try {
    globalThis.sessionStorage.setItem(key, value);
  } catch {
    // Some privacy modes disable sessionStorage. The in-memory session keeps
    // the current tab usable without persisting credentials elsewhere.
  }
}

function removeSession(key: string) {
  memorySession.delete(key);
  if (typeof window === "undefined") return;
  try {
    globalThis.sessionStorage.removeItem(key);
  } catch {
    // The in-memory copy has already been removed.
  }
}

function requireApiBase() {
  if (!API_BASE_VALID) {
    throw new Error("后端服务地址未配置或格式不正确");
  }
}

async function fetchApi(url: string, init: RequestInit) {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("API 连接超时，请检查 Railway 服务状态");
    }
    if (error instanceof TypeError) {
      throw new Error("无法连接 API，请检查 Railway 状态与 CORS 配置");
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function hasSession() {
  return typeof window !== "undefined" && Boolean(readSession(REFRESH));
}

export function clearSession() {
  removeSession(ACCESS);
  removeSession(REFRESH);
}

function save(tokens: Tokens) {
  writeSession(ACCESS, tokens.access_token);
  writeSession(REFRESH, tokens.refresh_token);
}

export async function login(
  email: string,
  password: string,
): Promise<SessionUser> {
  requireApiBase();
  const response = await fetchApi(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 429
        ? "登录失败次数过多，账号已临时锁定"
        : "邮箱或密码错误",
    );
  }
  const tokens: Tokens = await response.json();
  save(tokens);
  return tokens.user;
}

async function performRefresh(): Promise<boolean> {
  const refresh_token = readSession(REFRESH);
  if (!refresh_token) return false;
  const response = await fetchApi(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!response.ok) return false;
  save(await response.json());
  return true;
}

function refreshAccess(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function expireSession() {
  clearSession();
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  requireApiBase();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = readSession(ACCESS);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetchApi(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 401 && retry && (await refreshAccess())) {
    return api<T>(path, init, false);
  }
  if (response.status === 401) {
    expireSession();
    throw new Error("登录已失效，请重新登录");
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      message = (await response.json()).detail || message;
    } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function logout() {
  const refresh_token = readSession(REFRESH);
  try {
    if (refresh_token) {
      await api("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token }),
      });
    }
  } catch {
  } finally {
    clearSession();
  }
}
