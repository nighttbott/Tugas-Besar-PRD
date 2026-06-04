/**
 * lib/api.ts
 * Typed fetch wrapper for the FastAPI parking backend.
 * All authenticated requests include Authorization: Bearer <token>.
 *
 * In development, use ANPR_SERVICE_TOKEN from backend .env as the token
 * (it has both anpr_service + dashboard_user accepted by require_dashboard_token).
 * In production, use create_dashboard_token(nim, settings) from backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_BASE  = process.env.NEXT_PUBLIC_WS_URL  ?? "ws://localhost:8000";

// ── Core types ────────────────────────────────────────────────────────────────

export type VehicleType = "motor" | "mobil";
export type VehicleStatus = "active" | "inactive" | "blocked";
export type GateAction = "open_gate" | "deny_access" | "cooldown" | "low_confidence";
export type GateEventType = "gate_entry" | "gate_exit";

export interface EWallet {
  provider: string;
  balance: number;
  masked_account?: string;
}

export interface Vehicle {
  plate_normalized: string;   // "D4321ITB"
  plate_raw: string;          // "D 4321 ITB"
  nim: string;
  owner: string;
  vehicle_type: VehicleType;
  model: string;
  status: VehicleStatus;
  anpr_verified: boolean;
  verification_status: "pending" | "verified" | "flagged" | "blocked";
  flag_reason:         string | null;
  ewallet: EWallet | null;
  ewallet_backup: EWallet | null;
  is_parked: boolean;
  active_session: ActiveSession | null;
  ewallets: { provider: string; balance: number; is_primary: boolean; masked_account?: string }[];
}

export interface ActiveSession {
  plate_normalized: string;
  plate_raw: string;
  model: string;
  vehicle_type: VehicleType;
  gate_id: string;
  entry_time: string;
  entry_ts: number;
  elapsed_secs: number;
  duration_label: string;
  est_fee: number;
  est_fee_label: string;
  primary_ewallet: EWallet | null;  // matches backend field name exactly
  ewallet?: EWallet | null;
}

export interface SessionStats {
  total_vehicles: number;
  active_sessions: ActiveSession[];
  active_count: number;
  today_completed: number;
}

export interface GateEvent {
  type: GateEventType;
  plate: string;
  plate_raw: string;
  gate_id: string;
  owner: string;
  vehicle_model: string;
  confidence: number;
  timestamp: string;
  duration_secs?: number;
  fee?: number;
}

export interface SystemStatus {
  api: string;
  dashboard_clients: number;
  online_gates: string[];
}

export interface AddVehiclePayload {
  plate_number: string;
  vehicle_type: VehicleType;
  model: string;
  nim?: string;
}

export interface ApiError {
  detail: string;
}

// ── Internal fetch helper ─────────────────────────────────────────────────────

let _cachedToken: string | null = null;

export function setToken(token: string) {
  _cachedToken = token;
  if (typeof window !== "undefined") {
    localStorage.setItem("parking_token", token);
  }
}

export function clearToken() {
  _cachedToken = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("parking_token");
    localStorage.removeItem("parking_user");
  }
}

export function getStoredUser(): { nim: string; name: string } | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("parking_user");
  return raw ? JSON.parse(raw) : null;
}

export function setStoredUser(nim: string, name: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem("parking_user", JSON.stringify({ nim, name }));
  }
}

export async function getToken(): Promise<string | null> {
  if (_cachedToken) return _cachedToken;

  // Cek localStorage dulu (user sudah login sebelumnya)
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("parking_token");
    if (stored) { _cachedToken = stored; return _cachedToken; }
  }

  return null;
}

export async function loginUser(nim: string, password: string): Promise<{ nim: string; name: string }> {
  _cachedToken = null;
  const res = await fetch(`${API_BASE}/api/v1/auth/user-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nim, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? "Login gagal.");
  }
  const data = await res.json();
  setToken(data.access_token);
  setStoredUser(data.nim, data.name);
  _cachedToken = data.access_token;
  return { nim: data.nim, name: data.name };
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const resolvedToken = token ?? await getToken();   // ← auto-inject
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(resolvedToken ? { Authorization: `Bearer ${resolvedToken}` } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> ?? {}) },
  });

  if (!res.ok) {
    const body: ApiError = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Vehicle API ───────────────────────────────────────────────────────────────

export const vehicleApi = {
  list: (nim = "2021184750"): Promise<Vehicle[]> =>
    apiFetch<Vehicle[]>(`/api/v1/vehicles/?nim=${nim}`),

  add: (payload: AddVehiclePayload) =>
    apiFetch(`/api/v1/vehicles/`, { method: "POST", body: JSON.stringify(payload) }),

  delete: (plate: string) =>
    apiFetch(`/api/v1/vehicles/${encodeURIComponent(plate)}`, { method: "DELETE" }),

  sessions: (nim = "2021184750"): Promise<SessionStats> =>
    apiFetch<SessionStats>(`/api/v1/vehicles/sessions?nim=${nim}`),
};

// ── Gate API ──────────────────────────────────────────────────────────────────

export const gateApi = {
  getStatus: (): Promise<SystemStatus> =>
    apiFetch<SystemStatus>("/api/v1/gate/status"),

  getHistory: (limit = 50): Promise<unknown[]> =>
    apiFetch(`/api/v1/gate/history?limit=${limit}`),
};

// ── WebSocket URL builder ─────────────────────────────────────────────────────

export async function buildGateEventsWsUrl(): Promise<string> {
  const token = await getToken();
  return `${WS_BASE}/ws/gate-events?token=${encodeURIComponent(token ?? "")}`;
}

// ── Indonesian plate validator (client-side mirror of backend regex) ───────────

const PLATE_RE = /^[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{1,3}$/;

export interface PlateValidation {
  valid: boolean;
  error?: string;
  normalized?: string;   // "D4321ITB"
  formatted?: string;    // "D 4321 ITB"
}

export function validatePlate(raw: string): PlateValidation {
  const cleaned = raw.trim().toUpperCase();

  if (!cleaned) {
    return { valid: false, error: "Plat nomor tidak boleh kosong." };
  }
  if (cleaned.length < 4) {
    return { valid: false, error: "Plat nomor terlalu pendek." };
  }
  if (!PLATE_RE.test(cleaned)) {
    return {
      valid: false,
      error: "Format tidak valid. Contoh: B 1234 ABC, D 4321 ITB, AB 12 CD",
    };
  }

  const normalized = cleaned.replace(/\s/g, "");
  const match = normalized.match(/^([A-Z]{1,2})(\d{1,4})([A-Z]{1,3})$/);
  const formatted = match ? `${match[1]} ${match[2]} ${match[3]}` : normalized;

  return { valid: true, normalized, formatted };
}
