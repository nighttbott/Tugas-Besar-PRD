/**
 * components/parking/VehicleCard.tsx
 * Vehicle row with:
 *   • Inline model/merk name editing (user — PATCH /vehicles/{plate}/model)
 *   • Plate number shown as read-only with tooltip (edit requires admin)
 *   • Full e-wallet management panel
 *   • Status badge logic: "Aktif" only when anpr_verified=true AND status=active
 */
"use client";

import Image from "next/image";
import { useState, useMemo } from "react";
import type { Vehicle } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { useUpdateVehicleModel } from "@/hooks/useUpdateVehicleModel";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── E-wallet metadata ─────────────────────────────────────────────────────────
const EWALLET_OPTIONS = [
  { name: "GoPay",     logo: "/img/ewallet/gopay-baru.png",     bgColor: "#ffffff" },
  { name: "OVO",       logo: "/img/ewallet/ovo-baru.png",       bgColor: "#ffffff" },
  { name: "ShopeePay", logo: "/img/ewallet/shopeepay-baru.png", bgColor: "#ffffff" },
  { name: "Dana",      logo: "/img/ewallet/dana-baru.png",      bgColor: "#ffffff" },
  { name: "LinkAja",   logo: "/img/ewallet/linkaja-baru.png",   bgColor: "#ffffff" },
];

function ewalletMeta(name: string) {
  return EWALLET_OPTIONS.find((e) => e.name === name)
    ?? { name, logo: null as string | null, bgColor: "#888" };
}

// ── E-wallet logo ─────────────────────────────────────────────────────────────
function EwalletLogo({ name, size = 32 }: { name: string; size?: number }) {
  const meta = ewalletMeta(name);
  const [imgError, setImgError] = useState(false);

  if (meta.logo && !imgError) {
    return (
      <div style={{
        width: size, height: size, borderRadius: "50%",
        overflow: "hidden", flexShrink: 0, background: meta.bgColor,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Image
          src={meta.logo} alt={name} width={size} height={size}
          style={{ objectFit: "cover", width: "100%", height: "100%" }}
          onError={() => setImgError(true)}
        />
      </div>
    );
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", background: meta.bgColor,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: Math.round(size * 0.4), color: "#fff", fontWeight: 700, flexShrink: 0,
    }}>
      {name[0]}
    </div>
  );
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface Ewallet {
  provider:       string;
  balance:        number;
  masked_account: string;
  is_primary:     boolean;
}

interface VehicleCardProps {
  vehicle:    Vehicle;
}

// ─────────────────────────────────────────────────────────────────────────────
export function VehicleCard({ vehicle }: VehicleCardProps) {
  const queryClient = useQueryClient();
  
  // ── E-wallet panel state ───────────────────────────────────────────────────
  const [showEwallet,     setShowEwallet]     = useState(false);
  const [busy,            setBusy]            = useState(false);
  const [msg,             setMsg]             = useState<{ ok: boolean; text: string } | null>(null);
  const [addAccount,      setAddAccount]      = useState("");
  const [addBalance,      setAddBalance]      = useState("100000");
  const [addPrimary,      setAddPrimary]      = useState(false);
  const [editBalanceProv, setEditBalanceProv] = useState<string | null>(null);
  const [editBalanceVal,  setEditBalanceVal]  = useState("");

  // ── Model edit state ───────────────────────────────────────────────────────
  const [editingModel, setEditingModel] = useState(false);
  const [modelVal,     setModelVal]     = useState(vehicle.model);
  const [modelMsg,     setModelMsg]     = useState<{ ok: boolean; text: string } | null>(null);

  const [token, setToken] = useState<string | null>(null);
  useState(() => {
    import("@/lib/api").then(api => api.getToken().then(setToken));
  });
  const { mutateAsync: updateModel, isPending: modelBusy } = useUpdateVehicleModel(token);

  // ── Provider selection ─────────────────────────────────────────────────────
  const availableToAdd = useMemo(
    () => EWALLET_OPTIONS.filter((opt) => !vehicle.ewallets.some((e) => e.provider === opt.name)),
    [vehicle.ewallets]
  );
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const addProvider = useMemo(() => {
    const stillAvailable = availableToAdd.find((o) => o.name === selectedProvider);
    return stillAvailable?.name ?? availableToAdd[0]?.name ?? "";
  }, [availableToAdd, selectedProvider]);


  const plate = vehicle.plate_normalized;

  // Badge logic: "Aktif" only when BOTH verified AND active
  const displayActive  = vehicle.status === "active" && vehicle.verification_status === "verified";
  const displayBlocked = vehicle.status === "blocked";

  // ── Generic API call ───────────────────────────────────────────────────────
  async function api(method: string, path: string, body?: object) {
    const { getToken } = await import("@/lib/api");
    const t = await getToken();
    
    const res = await fetch(`${API}/api/v1/vehicles/${path}`, {
      method,
      headers: new Headers({
        "Content-Type": "application/json",
        ...(t ? { "Authorization": `Bearer ${t}` } : {}),
      }),
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) console.error("API error:", JSON.stringify(data));
    if (!res.ok) throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail) ?? "Terjadi kesalahan."
    );
    return data;
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Error." });
    } finally {
      setBusy(false);
    }
  }

  // ── Model edit handlers ────────────────────────────────────────────────────
  const handleStartEditModel = () => {
    setModelVal(vehicle.model);
    setModelMsg(null);
    setEditingModel(true);
  };

  const handleCancelEditModel = () => {
    setEditingModel(false);
    setModelVal(vehicle.model);
    setModelMsg(null);
  };

  const handleSaveModel = async () => {
    const trimmed = modelVal.trim();
    if (!trimmed || trimmed.length < 2) {
      setModelMsg({ ok: false, text: "Nama kendaraan minimal 2 karakter." });
      return;
    }
    if (trimmed === vehicle.model) {
      setEditingModel(false);
      return;
    }
    setModelMsg(null);
    try {
      await updateModel({ plate, model: trimmed });
      setModelMsg({ ok: true, text: "Model berhasil diperbarui." });
      setEditingModel(false);
    } catch (e: unknown) {
      setModelMsg({ ok: false, text: e instanceof Error ? e.message : "Gagal menyimpan." });
    }
  };

  // ── E-wallet handlers ──────────────────────────────────────────────────────
  const handleDelete = () => {
    if (!confirm(`Hapus kendaraan ${vehicle.plate_raw}?`)) return;
    run(() => api("DELETE", plate).then(() => {}));
  };

  const handleAddEwallet = () => {
    if (!addProvider) { setMsg({ ok: false, text: "Pilih provider e-wallet." }); return; }
    run(() =>
      api("POST", `${plate}/ewallet`, {
        provider:        addProvider,
        masked_account:  addAccount || "",
        initial_balance: parseInt(addBalance) || 0,
        set_as_primary:  addPrimary,
      }).then(() => { setAddAccount(""); setAddBalance("100000"); setAddPrimary(false); setSelectedProvider(""); })
    );
  };

  const handleRemoveEwallet = (provider: string) => {
    if (!confirm(`Hapus ${provider}?`)) return;
    run(() => api("DELETE", `${plate}/ewallet/${provider}`).then(() => {}));
  };

  const handleSetPrimary = (provider: string) =>
    run(() => api("PUT", `${plate}/ewallet/${provider}/primary`).then(() => {}));

  const handleUpdateBalance = (provider: string) =>
    run(() =>
      api("PUT", `${plate}/ewallet/${provider}/balance`, { balance: parseInt(editBalanceVal) || 0 })
        .then(() => { setEditBalanceProv(null); setEditBalanceVal(""); })
    );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ borderBottom: "1px solid #f0f0f0" }}>

      {/* ── Main vehicle row ── */}
      <div className="vehicle-row" style={{ borderBottom: "none" }}>
        <div className="v-left">
          {/* Plate — read-only with lock icon and tooltip */}
          <div style={{ position: "relative", flexShrink: 0 }}>
            <span className="plate">{vehicle.plate_raw}</span>
            <span
              title="Perubahan plat nomor hanya dapat dilakukan oleh admin. Hubungi petugas parkir."
              style={{
                position: "absolute",
                top: -6,
                right: -8,
                background: "#777",
                borderRadius: "50%",
                width: 14,
                height: 14,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "help",
                fontSize: 8,
                color: "#fff",
                fontWeight: 700,
                fontFamily: "sans-serif",
                lineHeight: 1,
              }}
            >
              🔒
            </span>
          </div>

          {/* Model name — editable inline */}
          <div>
            {editingModel ? (
              /* ── Edit mode ── */
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <input
                    type="text"
                    value={modelVal}
                    onChange={(e) => { setModelVal(e.target.value); setModelMsg(null); }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveModel();
                      if (e.key === "Escape") handleCancelEditModel();
                    }}
                    style={{
                      fontSize: 13, fontWeight: 600, color: "#333",
                      border: "1px solid #337ab7", borderRadius: 3,
                      padding: "3px 7px", width: 160,
                      boxShadow: "0 0 0 2px rgba(51,122,183,0.15)",
                      fontFamily: "'Roboto', sans-serif",
                    }}
                    maxLength={60}
                    autoFocus
                    disabled={modelBusy}
                  />
                  <button
                    type="button"
                    className="btn btn-blue"
                    style={{ padding: "3px 10px", fontSize: 12 }}
                    onClick={handleSaveModel}
                    disabled={modelBusy}
                  >
                    {modelBusy ? "..." : "Simpan"}
                  </button>
                  <button
                    type="button"
                    className="btn-link"
                    style={{ fontSize: 12 }}
                    onClick={handleCancelEditModel}
                    disabled={modelBusy}
                  >
                    Batal
                  </button>
                </div>
                {modelMsg && (
                  <div style={{ fontSize: 11, color: modelMsg.ok ? "#27ae60" : "#c0392b", marginTop: 2 }}>
                    {modelMsg.text}
                  </div>
                )}
              </div>
            ) : (
              /* ── View mode ── */
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 14, color: "#333" }}>
                    {vehicle.model}
                    {vehicle.is_parked && (
                      <span className="badge badge-blue" style={{ marginLeft: 8, fontSize: 10, verticalAlign: "middle" }}>
                        Sedang Parkir
                      </span>
                    )}
                  </span>
                  {/* Edit pencil button — only in view mode, not while parked */}
                  {!vehicle.is_parked && (
                    <button
                      type="button"
                      title="Edit nama kendaraan"
                      onClick={handleStartEditModel}
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        padding: "1px 4px",
                        borderRadius: 3,
                        color: "#aaa",
                        fontSize: 12,
                        lineHeight: 1,
                        display: "flex",
                        alignItems: "center",
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "#337ab7"; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "#aaa"; }}
                    >
                      ✏️
                    </button>
                  )}
                </div>
                {/* Success message shown briefly after save */}
                {modelMsg?.ok && (
                  <div style={{ fontSize: 11, color: "#27ae60", marginTop: 2 }}>
                    {modelMsg.text}
                  </div>
                )}
                <div className="v-meta">
                  {vehicle.vehicle_type === "motor" ? "Motor" : "Mobil"}
                  {vehicle.ewallets.length > 0 ? (
                    <> &bull; {vehicle.ewallets.map((e) => e.provider).join(", ")} terhubung</>
                  ) : (
                    <> &bull; <span style={{ color: "#c0392b" }}>Belum ada e-wallet</span></>
                  )}
                  {vehicle.verification_status === "verified" ? (
                    <> &bull; <span style={{ color: "#27ae60" }}>✓ Terverifikasi</span></>
                  ) : vehicle.verification_status === "flagged" ? (
                    <> &bull; <span style={{ color: "#c0392b" }}>⚠ Ditandai — {vehicle.flag_reason ?? ""}</span></>
                  ) : (
                    <> &bull; <span style={{ color: "#e67e22" }}>⏳ Menunggu verifikasi fisik</span></>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: badge + buttons */}
        <div className="v-actions">
          <span className={`badge ${displayActive ? "badge-green" : displayBlocked ? "badge-red" : "badge-orange"}`}>
            {displayActive ? "Aktif" : displayBlocked ? "Diblokir" : "Belum Aktif"}
          </span>
          <button
            type="button"
            className="btn btn-outline-blue"
            onClick={() => { setShowEwallet(!showEwallet); setMsg(null); }}
            disabled={busy}
          >
            {vehicle.ewallets.length > 0 ? "Kelola E-Wallet" : "Hubungkan E-Wallet"}
          </button>
          <button
            type="button"
            className="btn btn-outline-red"
            onClick={handleDelete}
            disabled={busy || vehicle.is_parked}
            style={{ opacity: vehicle.is_parked ? 0.5 : 1, cursor: vehicle.is_parked ? "not-allowed" : "pointer" }}
            title={vehicle.is_parked ? "Tidak dapat dihapus saat kendaraan sedang parkir" : ""}
          >
            Hapus
          </button>
        </div>
      </div>

      {/* Inline message (e-wallet errors) */}
      {msg && (
        <div
          className={`alert ${msg.ok ? "alert-success" : "alert-warn"}`}
          style={{ margin: "4px 0 8px", padding: "6px 12px", fontSize: 12 }}
        >
          {msg.text}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          E-WALLET MANAGEMENT PANEL
      ══════════════════════════════════════════════════════════════════ */}
      {showEwallet && (
        <div style={{
          background: "#f8fbff", border: "1px solid #c8dff5",
          borderRadius: 3, padding: "14px 16px", marginBottom: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <strong style={{ fontSize: 13, color: "#1a4a80" }}>
              Kelola E-Wallet — {vehicle.plate_raw}
            </strong>
            <button type="button" className="btn-link" onClick={() => setShowEwallet(false)}>
              Tutup
            </button>
          </div>

          {/* Existing e-wallets */}
          {vehicle.ewallets.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
              {vehicle.ewallets.map((ew) => {
                const isEditingBalance = editBalanceProv === ew.provider;
                return (
                  <div
                    key={ew.provider}
                    style={{
                      background: "#fff",
                      border: `1px solid ${ew.is_primary ? "#337ab7" : "#dde"}`,
                      borderRadius: 4, padding: "10px 14px", minWidth: 200,
                      boxShadow: ew.is_primary ? "0 0 0 2px rgba(51,122,183,0.15)" : "none",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <EwalletLogo name={ew.provider} size={30} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: "#333" }}>{ew.provider}</div>
                        <div style={{ fontSize: 11, color: "#888" }}>{ew.masked_account}</div>
                      </div>
                      <span className={`badge ${ew.is_primary ? "badge-blue" : "badge-gray"}`}>
                        {ew.is_primary ? "Primer" : "Cadangan"}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                      {isEditingBalance ? (
                        <>
                          <span style={{ fontSize: 11, color: "#555" }}>Rp</span>
                          <input
                            type="number" value={editBalanceVal}
                            onChange={(e) => setEditBalanceVal(e.target.value)}
                            style={{ width: 90, fontSize: 12, padding: "2px 6px", border: "1px solid #ccc", borderRadius: 3 }}
                            min={0} autoFocus
                          />
                          <button type="button" className="btn btn-blue"
                            style={{ padding: "2px 8px", fontSize: 11 }}
                            onClick={() => handleUpdateBalance(ew.provider)} disabled={busy}>
                            Simpan
                          </button>
                          <button type="button" className="btn-link" style={{ fontSize: 11 }}
                            onClick={() => { setEditBalanceProv(null); setEditBalanceVal(""); }}>
                            Batal
                          </button>
                        </>
                      ) : (
                        <>
                          <span style={{ fontSize: 13, fontWeight: 600, color: "#31708f" }}>
                            Rp{ew.balance.toLocaleString("id-ID")}
                          </span>
                          <button type="button" className="btn-link" style={{ fontSize: 11 }}
                            onClick={() => { setEditBalanceProv(ew.provider); setEditBalanceVal(String(ew.balance)); }}>
                            Edit Saldo
                          </button>
                        </>
                      )}
                    </div>

                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {!ew.is_primary && (
                        <button type="button" className="btn btn-outline-blue"
                          style={{ padding: "3px 8px", fontSize: 11 }}
                          onClick={() => handleSetPrimary(ew.provider)} disabled={busy}>
                          Jadikan Primer
                        </button>
                      )}
                      <button type="button" className="btn btn-outline-red"
                        style={{ padding: "3px 8px", fontSize: 11 }}
                        onClick={() => handleRemoveEwallet(ew.provider)} disabled={busy}>
                        Hapus
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Add new e-wallet */}
          {availableToAdd.length > 0 ? (
            <div style={{ background: "#fff", border: "1px solid #dde", borderRadius: 3, padding: "10px 14px" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#444", marginBottom: 8 }}>
                + Tambah E-Wallet
              </div>
              <div className="form-row" style={{ marginBottom: 6 }}>
                <div className="fg">
                  <label>Provider</label>
                  <select style={{ width: 130 }} value={addProvider}
                    onChange={(e) => setSelectedProvider(e.target.value)}>
                    {availableToAdd.map((opt) => (
                      <option key={opt.name} value={opt.name}>{opt.name}</option>
                    ))}
                  </select>
                </div>
                <div className="fg">
                  <label>No. HP / Akun (opsional)</label>
                  <input type="text" placeholder="081234567890" style={{ width: 155 }}
                    value={addAccount} onChange={(e) => setAddAccount(e.target.value)} maxLength={20} />
                </div>
                <div className="fg">
                  <label>Saldo Awal (Rp)</label>
                  <input type="number" style={{ width: 120 }} value={addBalance}
                    onChange={(e) => setAddBalance(e.target.value)} min={0} />
                </div>
                <div className="fg" style={{ justifyContent: "flex-end" }}>
                  <label style={{ visibility: "hidden" }}>x</label>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                      <input type="checkbox" checked={addPrimary}
                        onChange={(e) => setAddPrimary(e.target.checked)} />
                      Jadikan Primer
                    </label>
                    <button type="button" className="btn btn-blue"
                      onClick={handleAddEwallet} disabled={busy || !addProvider}>
                      Hubungkan
                    </button>
                  </div>
                </div>
              </div>
              <p className="hint">
                Saldo dapat diedit kapan saja. Autodebit mengurangi saldo primer dulu, lalu cadangan jika tidak cukup.
              </p>
            </div>
          ) : (
            <div style={{
              background: "#fff", border: "1px solid #dde", borderRadius: 3,
              padding: "12px 14px", textAlign: "center", color: "#888", fontSize: 13,
            }}>
              Semua provider e-wallet sudah terhubung ke kendaraan ini.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
