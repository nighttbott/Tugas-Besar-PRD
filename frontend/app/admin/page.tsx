/**
 * app/admin/page.tsx
 * Admin panel with:
 *   - ANPR verify / revoke
 *   - Plate number change (resets ANPR verification, requires re-verify)
 *   - Search                       filter
 *   - Stat cards
 */
"use client";

import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────
interface AdminVehicle {
  plate_normalized: string;
  plate_raw:        string;
  nim:              string;
  owner:            string;
  vehicle_type:     string;
  model:            string;
  status:           string;
  verification_status: "pending" | "verified" | "flagged" | "blocked";
  verified_at:         string | null;
  verified_gate:       string | null;
  flag_reason:         string | null;
  is_parked:        boolean;
  ewallets:         { provider: string; balance: number; is_primary: boolean }[];
}

interface ActiveSession {
  plate:          string;
  gate_id:        string;
  gate_location:  string;
  entry_time:     string;
  is_guest:       boolean;
  exit_approved:  boolean;
  owner:          string;
  model:          string;
  needs_manual_payment?: boolean;
}

// ── API helper ────────────────────────────────────────────────────────────────
async function apiFetch(path: string, token: string, method = "GET", body?: object) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization:  `Bearer ${token}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data;
}

// ── Plate validator (mirrors backend regex) ───────────────────────────────────
function normalizePlate(raw: string): string {
  return raw.toUpperCase().replace(/\s/g, "");
}
function isValidPlate(raw: string): boolean {
  return /^[A-Z]{1,2}\d{1,4}[A-Z]{1,3}$/.test(normalizePlate(raw));
}

// ═════════════════════════════════════════════════════════════════════════════
// LOGIN SCREEN
// ═════════════════════════════════════════════════════════════════════════════
function LoginScreen({ onLogin }: { onLogin: (token: string, adminId: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const handleLogin = async () => {
    if (!username || !password) { setError("Username dan password wajib diisi."); return; }
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/v1/admin/auth/token`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Login gagal.");
      onLogin(data.access_token, data.admin_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Login gagal.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh", background: "#f5f5f5",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Roboto', sans-serif",
    }}>
      <div style={{
        background: "#fff", border: "1px solid #ddd", borderRadius: 4,
        padding: "32px 36px", width: 380,
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{
            width: 48, height: 48, background: "#222", borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 12px",
          }}>
            <i className="fa fa-shield" style={{ color: "#fff", fontSize: 20 }} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: "#222", margin: 0 }}>Admin Parkir</h2>
          <p style={{ fontSize: 13, color: "#888", marginTop: 4 }}>ITB Jatinangor — Panel Administrasi</p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="fg">
            <label>Username</label>
            <input type="text" placeholder="admin" value={username} autoFocus autoComplete="username"
              style={{ width: "100%" }}
              onChange={(e) => { setUsername(e.target.value); setError(null); }}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()} />
          </div>
          <div className="fg">
            <label>Password</label>
            <input type="password" placeholder="••••••••" value={password} autoComplete="current-password"
              style={{ width: "100%" }}
              onChange={(e) => { setPassword(e.target.value); setError(null); }}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()} />
          </div>
          {error && (
            <div className="alert alert-warn" style={{ margin: 0, padding: "8px 12px", fontSize: 12 }}>
              {error}
            </div>
          )}
          <button type="button" className="btn btn-blue"
            onClick={handleLogin} disabled={loading}
            style={{ width: "100%", justifyContent: "center", padding: "9px 0", fontSize: 14, opacity: loading ? 0.7 : 1 }}>
            {loading ? "Masuk..." : "Masuk sebagai Admin"}
          </button>
        </div>
        <p style={{ fontSize: 11, color: "#bbb", textAlign: "center", marginTop: 20 }}>
          Halaman ini hanya untuk petugas parkir yang berwenang.
        </p>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// VEHICLE ROW
// ═════════════════════════════════════════════════════════════════════════════
function AdminVehicleRow({
  vehicle, token, onUpdated,
}: { vehicle: AdminVehicle; token: string; onUpdated: () => void }) {
  const [busy,        setBusy]        = useState(false);
  const [msg,         setMsg]         = useState<{ ok: boolean; text: string } | null>(null);
  const [showPlate,   setShowPlate]   = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [newNim,      setNewNim]      = useState("");
  const [newOwner,    setNewOwner]    = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [newPlate,    setNewPlate]    = useState("");
  const [plateErr,    setPlateErr]    = useState<string | null>(null);
  const [plateReason, setPlateReason] = useState("");
  const [forceTransfer, setForceTransfer] = useState(false);

  const handleTransfer = async () => {
    if (!newNim || !newOwner) { setMsg({ ok: false, text: "NIM dan nama wajib diisi." }); return; }
    if (!confirm(`Transfer ${vehicle.plate_raw} ke ${newOwner} (${newNim})?`)) return;
    setBusy(true); setMsg(null);
    try {
      const d = await apiFetch(
        `/api/v1/admin/vehicles/${vehicle.plate_normalized}/transfer?force=${forceTransfer}`,
        token, "POST",
        { new_nim: newNim, new_owner: newOwner, reason: transferReason }
      );
      setMsg({ ok: true, text: d.message });
      setShowTransfer(false); setNewNim(""); setNewOwner(""); setTransferReason("");
      setForceTransfer(false);
      onUpdated();
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Gagal transfer." });
    } finally { setBusy(false); }
  };

  const handleChangePlate = async () => {
    const normalized = normalizePlate(newPlate);
    if (!isValidPlate(newPlate)) { setPlateErr("Format plat tidak valid."); return; }
    if (normalized === vehicle.plate_normalized) { setPlateErr("Plat baru sama dengan plat saat ini."); return; }
    if (!confirm(`Ubah plat ${vehicle.plate_raw} → ${newPlate.toUpperCase()}?`)) return;

    setBusy(true); setMsg(null); setPlateErr(null);
    try {
      const d = await apiFetch(
        `/api/v1/admin/vehicles/${vehicle.plate_normalized}/plate`,
        token, "PATCH",
        { new_plate: normalized, reason: plateReason }
      );
      setMsg({ ok: true, text: d.message });
      setShowPlate(false); setNewPlate(""); setPlateReason("");
      onUpdated();
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Gagal mengubah plat." });
    } finally { setBusy(false); }
  };

  return (
    <tr>
      {/* Plate */}
      <td>
        <span className="plate" style={{ fontSize: 10, padding: "2px 9px", letterSpacing: "2px" }}>
          {vehicle.plate_raw}
        </span>
      </td>

      {/* Owner / NIM */}
      <td>
        <div style={{ fontWeight: 500, fontSize: 13 }}>{vehicle.owner}</div>
        <div style={{ fontSize: 11, color: "#888" }}>{vehicle.nim}</div>
      </td>

      {/* Vehicle */}
      <td>
        <div style={{ fontSize: 13 }}>{vehicle.model}</div>
        <div style={{ fontSize: 11, color: "#888", textTransform: "capitalize" }}>{vehicle.vehicle_type}</div>
      </td>

      {/* Status */}
      <td>
        <span style={{
          display: "inline-block", padding: "2px 8px", borderRadius: 10,
          fontSize: 11, fontWeight: 600,
          background: vehicle.status === "active" ? "#dff0d8" : vehicle.status === "inactive" ? "#fcf8e3" : "#f2dede",
          color:      vehicle.status === "active" ? "#27ae60" : vehicle.status === "inactive" ? "#e67e22" : "#e74c3c",
        }}>
          {vehicle.status === "active" ? "Aktif" : vehicle.status === "inactive" ? "Belum Aktif" : "Diblokir"}
        </span>
        {vehicle.is_parked && (
          <span className="badge badge-blue" style={{ marginLeft: 6, fontSize: 10 }}>Parkir</span>
        )}
        <div style={{ marginTop: 4 }}>
          <span style={{
            display: "inline-block", padding: "2px 7px", borderRadius: 10, fontSize: 10, fontWeight: 600,
            background: vehicle.verification_status === "verified" ? "#dff0d8"
                      : vehicle.verification_status === "flagged"  ? "#f2dede"
                      : "#fcf8e3",
            color:      vehicle.verification_status === "verified" ? "#27ae60"
                      : vehicle.verification_status === "flagged"  ? "#c0392b"
                      : "#e67e22",
          }}>
            {vehicle.verification_status === "verified" ? "✓ Verified"
           : vehicle.verification_status === "flagged"  ? "⚠ Flagged"
           : "⏳ Pending"}
          </span>
          {vehicle.verified_at && (
            <div style={{ fontSize: 10, color: "#aaa", marginTop: 2 }}>
              {new Date(vehicle.verified_at).toLocaleDateString("id-ID")} · {vehicle.verified_gate}
            </div>
          )}
        </div>
      </td>

      {/* E-Wallet */}
      <td style={{ fontSize: 12, color: "#555" }}>
        {vehicle.ewallets.length === 0 ? (
          <span style={{ color: "#c0392b" }}>Tidak ada</span>
        ) : vehicle.ewallets.map((e) => (
          <div key={e.provider}>
            {e.provider}
            {e.is_primary && <span style={{ color: "#888", fontSize: 10 }}> (primer)</span>}
            <span style={{ color: "#31708f", marginLeft: 4 }}>
              Rp{e.balance.toLocaleString("id-ID")}
            </span>
          </div>
        ))}
      </td>

      {/* Ubah Plat */}
      <td>
        {!showPlate ? (
          <button type="button"
            onClick={() => { setShowPlate(true); setNewPlate(""); setPlateErr(null); }}
            disabled={busy || vehicle.is_parked}
            title={vehicle.is_parked ? "Tidak bisa ubah plat saat parkir" : ""}
            style={{
              background: "transparent", border: "1px solid #aaa", color: "#555",
              borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
              opacity: vehicle.is_parked ? 0.5 : 1,
              display: "flex", alignItems: "center", gap: 4,
            }}>
            <i className="fa fa-edit" style={{ fontSize: 10 }} />
            Ubah Plat
          </button>
        ) : (
        <>
          <label style={{ fontSize: 11, color: "#e67e22", display: "flex", alignItems: "center", gap: 5 }}>
            <input type="checkbox"
              checked={forceTransfer}
              onChange={(e) => setForceTransfer(e.target.checked)} />
            Force (kendaraan sedang parkir)
          </label>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <input type="text" placeholder="D 1234 AB" value={newPlate} maxLength={12} autoFocus
              onChange={(e) => { setNewPlate(e.target.value.toUpperCase()); setPlateErr(null); }}
              onKeyDown={(e) => e.key === "Escape" && setShowPlate(false)}
              style={{
                fontSize: 12, padding: "3px 7px", borderRadius: 3,
                border: `1px solid ${plateErr ? "#c0392b" : "#ccc"}`,
                textTransform: "uppercase", letterSpacing: 1,
              }} />
            {plateErr && <div style={{ fontSize: 10.5, color: "#c0392b" }}>{plateErr}</div>}
            <input type="text" placeholder="Alasan (opsional)" value={plateReason}
              onChange={(e) => setPlateReason(e.target.value)}
              style={{ fontSize: 11, padding: "3px 7px", borderRadius: 3, border: "1px solid #ccc" }} />
            <div style={{ display: "flex", gap: 5 }}>
              <button type="button" onClick={handleChangePlate} disabled={busy || !newPlate}
                style={{
                  background: "#e67e22", color: "#fff", border: "none",
                  borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
                  opacity: !newPlate ? 0.5 : 1,
                }}>
                Simpan
              </button>
              <button type="button"
                onClick={() => { setShowPlate(false); setNewPlate(""); setPlateErr(null); }}
                style={{
                  background: "transparent", border: "1px solid #ccc", color: "#777",
                  borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
                }}>
                Batal
              </button>
            </div>
          </div>
        </>
        )}

        {/* Transfer kepemilikan */}
        <div style={{ borderTop: "1px solid #f0f0f0", paddingTop: 6, marginTop: 6 }}>
          {!showTransfer ? (
            <button type="button"
              onClick={() => { setShowTransfer(true); setNewNim(""); setNewOwner(""); }}
              disabled={busy || vehicle.is_parked}
              style={{
                background: "transparent", border: "1px solid #aaa", color: "#555",
                borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
                opacity: vehicle.is_parked ? 0.5 : 1,
                display: "flex", alignItems: "center", gap: 4,
              }}>
              <i className="fa fa-exchange" style={{ fontSize: 10 }} />
              Transfer
            </button>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ fontSize: 10.5, color: "#337ab7", fontWeight: 600 }}>
                Transfer Kepemilikan
              </div>
              <input type="text" placeholder="NIM baru" value={newNim}
                onChange={(e) => setNewNim(e.target.value)}
                style={{ fontSize: 11, padding: "3px 7px", borderRadius: 3, border: "1px solid #ccc" }}
                autoFocus />
              <input type="text" placeholder="Nama pemilik baru" value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
                style={{ fontSize: 11, padding: "3px 7px", borderRadius: 3, border: "1px solid #ccc" }} />
              <input type="text" placeholder="Alasan (opsional)" value={transferReason}
                onChange={(e) => setTransferReason(e.target.value)}
                style={{ fontSize: 11, padding: "3px 7px", borderRadius: 3, border: "1px solid #ccc" }} />
              <div style={{ display: "flex", gap: 5 }}>
                <button type="button" onClick={handleTransfer}
                  disabled={busy || !newNim || !newOwner}
                  style={{
                    background: "#337ab7", color: "#fff", border: "none",
                    borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
                    opacity: (!newNim || !newOwner) ? 0.5 : 1,
                  }}>
                  Transfer
                </button>
                <button type="button"
                  onClick={() => { setShowTransfer(false); setNewNim(""); setNewOwner(""); }}
                  style={{
                    background: "transparent", border: "1px solid #ccc", color: "#777",
                    borderRadius: 3, padding: "3px 9px", fontSize: 11, cursor: "pointer",
                  }}>
                  Batal
                </button>
              </div>
            </div>
          )}
        </div>

        {msg && (
          <div style={{
            fontSize: 11, padding: "3px 8px", borderRadius: 3, marginTop: 4,
            background: msg.ok ? "#dff0d8" : "#f2dede",
            color:      msg.ok ? "#27ae60"  : "#c0392b",
          }}>
            {msg.text}
          </div>
        )}
      </td>
    </tr>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// ADMIN DASHBOARD
// ═════════════════════════════════════════════════════════════════════════════
function AdminDashboard({
  token, adminId, onLogout,
}: { token: string; adminId: string; onLogout: () => void }) {
  const [vehicles,     setVehicles]     = useState<AdminVehicle[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [search,       setSearch]       = useState("");
  const [sessions,     setSessions]     = useState<ActiveSession[]>([]);
  const [sessLoading,  setSessLoading]  = useState(false);
  const [approving,    setApproving]    = useState<string | null>(null);
  const [paymentPlate,  setPaymentPlate]  = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<string | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);


  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await apiFetch("/api/v1/admin/vehicles", token);
      setVehicles(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memuat data.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadSessions = useCallback(async () => {
    setSessLoading(true);
    console.log("loadSessions called");
    try {
      const data = await apiFetch("/api/v1/admin/sessions", token);
      setSessions(data);
      console.log("sessions loaded:", data);
    } catch (e){ 
      console.error("sessions error:", e);
    }
    finally { setSessLoading(false); }
  }, [token]);

  const handleApproveExit = async (plate: string, method: string) => {
    setPaymentLoading(true);
    setPaymentMethod(method);
    // Simulasi proses pembayaran 5 detik
    await new Promise((res) => setTimeout(res, 5000));
    try {
      await apiFetch(`/api/v1/admin/sessions/${plate}/approve-exit`, token, "POST");
      await loadSessions();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Gagal.");
    } finally {
      setPaymentLoading(false);
      setPaymentPlate(null);
      setPaymentMethod(null);
    }
  };  

  useEffect(() => { load(); loadSessions(); }, [load, loadSessions]);

  const filtered = vehicles.filter((v) => {
    const q = search.toLowerCase();
    return !q ||
      v.plate_raw.toLowerCase().includes(q) ||
      v.owner.toLowerCase().includes(q) ||
      v.nim.includes(q) ||
      v.model.toLowerCase().includes(q);
  });

  const totalParked  = vehicles.filter((v) => v.is_parked).length;
  const totalGuest   = sessions.filter((s) => s.is_guest).length;
  const totalSession = sessions.length;
  return (
    <div style={{ minHeight: "100vh", background: "#f5f5f5", fontFamily: "'Roboto', sans-serif" }}>

      {/* Topbar */}
      <nav style={{
        background: "#222", borderBottom: "1px solid #080808", height: 50,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px", position: "sticky", top: 0, zIndex: 1030,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ color: "#9d9d9d", fontSize: 18, fontWeight: 400, letterSpacing: 0.5 }}>SIX</span>
          <i className="fa fa-home" style={{ color: "#9d9d9d", fontSize: 14 }} />
          <span style={{ color: "#666", fontSize: 13, marginLeft: 8, borderLeft: "1px solid #444", paddingLeft: 12 }}>
            Panel Admin Parkir
          </span>
          <span style={{
            background: "#c0392b", color: "#fff", fontSize: 10, fontWeight: 700,
            padding: "2px 7px", borderRadius: 10, letterSpacing: 0.5, marginLeft: 4,
          }}>ADMIN</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ color: "#9d9d9d", fontSize: 13 }}>
            <i className="fa fa-user-circle-o" style={{ marginRight: 6 }} />
            {adminId}
          </span>
          <button type="button" onClick={onLogout}
            style={{
              background: "transparent", border: "1px solid #555", color: "#9d9d9d",
              borderRadius: 3, padding: "4px 12px", fontSize: 12, cursor: "pointer",
              fontFamily: "'Roboto', sans-serif", display: "flex", alignItems: "center", gap: 5,
            }}>
            <i className="fa fa-sign-out" style={{ fontSize: 12 }} />
            Keluar
          </button>
        </div>
      </nav>

      {/* Content */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px" }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 26, fontWeight: 300, color: "#036", margin: "0 0 4px" }}>
            Manajemen Kendaraan
          </h1>
          <p style={{ fontSize: 13, color: "#888", margin: 0 }}>
            ITB Jatinangor — Verifikasi ANPR &amp; Perubahan Plat Nomor
          </p>
        </div>

        {/* Stat cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "Total Kendaraan",  value: vehicles.length, color: "#31708f", bg: "#d9edf7" },
            { label: "Sedang Parkir",    value: totalSession,    color: "#337ab7", bg: "#d9edf7" },
            { label: "Kendaraan Tamu",   value: totalGuest,      color: "#e67e22", bg: "#fcf8e3" },
            { label: "Terdaftar Parkir", value: totalParked,     color: "#27ae60", bg: "#dff0d8" },
          ].map((s) => (
            <div key={s.label} style={{
              background: "#fff", border: `1px solid ${s.bg}`,
              borderRadius: 4, padding: "14px 16px", textAlign: "center",
            }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 12, color: "#777", marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Filter bar */}
        <div style={{
          background: "#fff", border: "1px solid #dde", borderRadius: "4px 4px 0 0",
          padding: "12px 16px", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
          borderBottom: "none",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, flex: 1, minWidth: 200 }}>
            <i className="fa fa-search" style={{ color: "#aaa", fontSize: 13 }} />
            <input type="text" placeholder="Cari plat, nama, NIM, model..."
              value={search} onChange={(e) => setSearch(e.target.value)}
              style={{
                border: "none", outline: "none", fontSize: 13, width: "100%",
                fontFamily: "'Roboto', sans-serif", color: "#333",
              }} />
          </div>
          <button type="button" onClick={load} disabled={loading}
            style={{
              background: "#fff", border: "1px solid #ddd", borderRadius: 3,
              padding: "4px 12px", fontSize: 12, 
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.6 : 1,
              fontFamily: "'Roboto', sans-serif", color: "#555",
              display: "flex", alignItems: "center", gap: 5,
            }}>
            <i className={`fa fa-refresh ${loading ? "fa-spin" : ""}`} style={{ fontSize: 12 }} />
            Refresh
          </button>
        </div>

        {/* Table */}
        <div className="panel" style={{ marginBottom: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
          <div className="panel-head">
            Daftar Kendaraan
            <span className="badge badge-blue" style={{ marginLeft: 10, fontWeight: 400, fontSize: 11 }}>
              {filtered.length} kendaraan
            </span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: "28px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
                <i className="fa fa-spinner fa-spin" style={{ marginRight: 8 }} />
                Memuat data...
              </div>
            ) : error ? (
              <div className="alert alert-warn" style={{ margin: 16 }}>{error}</div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: "28px 0", textAlign: "center", color: "#aaa", fontSize: 13 }}>
                Tidak ada kendaraan yang sesuai filter.
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 120 }}>Plat Nomor</th>
                    <th style={{ width: 160 }}>Pemilik / NIM</th>
                    <th style={{ width: 150 }}>Kendaraan</th>
                    <th style={{ width: 130 }}>Status & Verifikasi</th>
                    <th style={{ width: 160 }}>E-Wallet</th>
                    <th style={{ width: 160 }}>Ubah Plat</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((v) => (
                    <AdminVehicleRow key={v.plate_normalized} vehicle={v} token={token} onUpdated={load} />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Session Aktif */}
        {sessions.map((s) => {
          const entryTime = new Date(s.entry_time).toLocaleTimeString("id-ID", {
            hour: "2-digit", minute: "2-digit",
          });
          const isApproving = approving === s.plate;
          const isGuest = s.is_guest || s.owner === "Tamu";

          return (
            <div key={s.plate} style={{
              background: "#fff",
              border: `1px solid ${isGuest ? "#f0ad4e" : "#dde"}`,
              borderRadius: 4, padding: "12px 16px",
              display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
            }}>
              <span className="plate" style={{ fontSize: 10, padding: "2px 8px", letterSpacing: "1.5px" }}>
                {s.plate}
              </span>
              <div style={{ flex: 1, minWidth: 160 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#333" }}>
                  {s.owner}{s.model !== "–" && ` — ${s.model}`}
                </div>
                <div style={{ fontSize: 11, color: "#888" }}>
                  Masuk {entryTime} · {s.gate_location}
                </div>
              </div>

              <span className={`badge ${isGuest ? "badge-orange" : "badge-green"}`}>
                {isGuest ? "Tamu" : "Terdaftar"}
              </span>

              {s.needs_manual_payment && !s.exit_approved && (
                <span className="badge" style={{ background: "#c0392b", color: "#fff" }}>
                  ⚠ Perlu Bayar Manual
                </span>
              )}

              {(isGuest || s.needs_manual_payment) && !s.exit_approved && (
                <>
                  {paymentPlate === s.plate ? (
                    paymentLoading ? (
                      <div style={{
                        display: "flex", alignItems: "center", gap: 10,
                        background: "#f8f9fa", border: "1px solid #dde",
                        borderRadius: 4, padding: "8px 14px", fontSize: 13,
                      }}>
                        <i className="fa fa-spinner fa-spin" style={{ color: "#337ab7" }} />
                        <span>Memproses <strong>{paymentMethod}</strong>...</span>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ fontSize: 12, color: "#555", fontWeight: 600 }}>Pilih metode pembayaran:</div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {["Cash", "QRIS", "Tap e-Money"].map((method) => (
                            <button key={method} type="button"
                              onClick={() => handleApproveExit(s.plate, method)}
                              style={{
                                background: "#fff", border: "1px solid #337ab7", color: "#337ab7",
                                borderRadius: 3, padding: "5px 12px", fontSize: 12, cursor: "pointer", fontWeight: 500,
                              }}>
                              {method === "Cash" ? "💵 Cash" : method === "QRIS" ? "📱 QRIS" : "💳 Tap e-Money"}
                            </button>
                          ))}
                          <button type="button" onClick={() => setPaymentPlate(null)}
                            style={{
                              background: "transparent", border: "1px solid #ccc", color: "#888",
                              borderRadius: 3, padding: "5px 10px", fontSize: 12, cursor: "pointer",
                            }}>
                            Batal
                          </button>
                        </div>
                      </div>
                    )
                  ) : (
                    <button type="button" onClick={() => setPaymentPlate(s.plate)}
                      style={{
                        background: "#27ae60", color: "#fff", border: "none",
                        borderRadius: 3, padding: "5px 12px", fontSize: 12, cursor: "pointer",
                      }}>
                      ✓ Izinkan Keluar
                    </button>
                  )}
                </>
              )}

              {(isGuest || s.needs_manual_payment) && !s.exit_approved && (
                <span className="badge badge-green">✓ Keluar Diizinkan</span>
              )}
            </div>
          );
        })}
      </div>

        <div className="alert alert-info" style={{ marginTop: 16 }}>
          <strong>Panduan:</strong> Kendaraan <strong>Tamu</strong> masuk tanpa registrasi — admin perlu klik <strong>Izinkan Keluar</strong> sebelum kamera exit bisa membuka gate. Kendaraan <strong>Terdaftar</strong> keluar otomatis via ANPR.
        </div>
        <p style={{ fontSize: 11, color: "#bbb", textAlign: "center", marginTop: 12 }}>
          Panel Admin — ITB Jatinangor Parking System &bull; Login sebagai: {adminId}
        </p>
        </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// ROOT
// ═════════════════════════════════════════════════════════════════════════════
export default function AdminPage() {
  const [token,    setToken]    = useState<string | null>(null);
  const [adminId,  setAdminId]  = useState("");
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const t  = sessionStorage.getItem("admin_token");
    const id = sessionStorage.getItem("admin_id");
    if (t && id) { setToken(t); setAdminId(id); }
    setRestored(true);
  }, []);

  const handleLogin = (t: string, id: string) => {
    setToken(t); setAdminId(id);
    sessionStorage.setItem("admin_token", t);
    sessionStorage.setItem("admin_id",    id);
  };

  const handleLogout = () => {
    setToken(null); setAdminId("");
    sessionStorage.removeItem("admin_token");
    sessionStorage.removeItem("admin_id");
  };

  if (!restored) return null;
  if (!token)    return <LoginScreen onLogin={handleLogin} />;
  return <AdminDashboard token={token} adminId={adminId} onLogout={handleLogout} />;
}
