export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

export type SessionUser = { id: string; email: string; full_name: string; role: "admin" | "analyst" | "sales" | "viewer"; is_active: boolean };
type Tokens = { access_token: string; refresh_token: string; user: SessionUser };

const ACCESS = "sales-intel-access";
const REFRESH = "sales-intel-refresh";

export function hasSession() { return typeof window !== "undefined" && Boolean(sessionStorage.getItem(REFRESH)); }
export function clearSession() { if (typeof window !== "undefined") { sessionStorage.removeItem(ACCESS); sessionStorage.removeItem(REFRESH); } }
function save(tokens: Tokens) { sessionStorage.setItem(ACCESS, tokens.access_token); sessionStorage.setItem(REFRESH, tokens.refresh_token); }

export async function login(email: string, password: string): Promise<SessionUser> {
  if (!API_BASE) throw new Error("未配置 NEXT_PUBLIC_API_BASE_URL");
  const response = await fetch(`${API_BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  if (!response.ok) throw new Error(response.status === 429 ? "登录失败次数过多，账号已临时锁定" : "邮箱或密码错误");
  const tokens: Tokens = await response.json(); save(tokens); return tokens.user;
}

async function refreshAccess(): Promise<boolean> {
  const refresh_token = sessionStorage.getItem(REFRESH); if (!refresh_token) return false;
  const response = await fetch(`${API_BASE}/api/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token }) });
  if (!response.ok) { clearSession(); return false; }
  save(await response.json()); return true;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  if (!API_BASE) throw new Error("后端服务地址未配置");
  const headers = new Headers(init.headers); headers.set("Content-Type", "application/json");
  const token = sessionStorage.getItem(ACCESS); if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 401 && retry && await refreshAccess()) return api<T>(path, init, false);
  if (!response.ok) { let message = `请求失败（${response.status}）`; try { message = (await response.json()).detail || message; } catch {} throw new Error(message); }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function logout() {
  const refresh_token = sessionStorage.getItem(REFRESH);
  try { if (refresh_token) await api("/api/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token }) }); } finally { clearSession(); }
}
