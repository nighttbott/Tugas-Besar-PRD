/**
 * app/parkir/page.tsx
 * Main parking page — fully connected to FastAPI backend.
 *
 * Data flows:
 *   • Vehicle list     → GET  /api/v1/vehicles/       (on mount + after add/delete)
 *   • Add vehicle      → POST /api/v1/vehicles/        (with Indonesian plate validation)
 *   • Delete vehicle   → DELETE /api/v1/vehicles/{plate} (via VehicleCard)
 *   • Status/stats     → GET  /api/v1/vehicles/sessions (via ParkingStatus)
 *   • History          → GET  /api/v1/gate/history     (via HistoryTable)
 *   • Live events      → WS   /ws/gate-events          (via LiveGateEvent)
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { Navbar }        from "@/components/layout/Navbar";
import { Breadcrumb }    from "@/components/layout/Breadcrumb";
import { TabMenu, type TabId } from "@/components/parking/TabMenu";
import { VehicleCard } from "@/components/parking/VehicleCard";
import { ParkingStatus } from "@/components/parking/ParkingStatus";
import { HistoryTable }  from "@/components/parking/HistoryTable";
import { TarifInfo }     from "@/components/parking/TarifInfo";
import { vehicleApi, validatePlate, type VehicleType, type Vehicle } from "@/lib/api";
import { getStoredUser, loginUser, clearToken } from "@/lib/api";


// Generate with: python -c "from core.security import create_dashboard_token; ..."

// ── Indonesian plate input formatter ─────────────────────────────────────────
function formatPlateInput(raw: string): string {
  // Auto-format as user types: "D1234ITB" → "D 1234 ITB"
  const clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const match = clean.match(/^([A-Z]{1,2})(\d{0,4})([A-Z]{0,3})$/);
  if (!match) return raw.toUpperCase().slice(0, 12);
  const parts = [match[1], match[2], match[3]].filter(Boolean);
  return parts.join(" ");
}

// ─────────────────────────────────────────────────────────────────────────────
export default function ParkirPage() {
  // User
  const [user, setUser] = useState<{ nim: string; name: string } | null>(null);
  const [loginNim, setLoginNim] = useState("");
  const [loginPass, setLoginPass] = useState("");
  const [loginErr, setLoginErr] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);

  // Vehicle
  const [activeTab,    setActiveTab]    = useState<TabId>("kendaraan");
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehiclesLoad, setVehiclesLoad] = useState(true);
  const [vehiclesErr,  setVehiclesErr]  = useState<string | null>(null);

  // Add vehicle form state
  const [newPlat,     setNewPlat]     = useState("");
  const [newPlatErr,  setNewPlatErr]  = useState<string | null>(null);
  const [newModel,    setNewModel]    = useState("");
  const [newJenis,    setNewJenis]    = useState<VehicleType>("motor");
  const [addLoading,  setAddLoading]  = useState(false);
  const [addMsg,      setAddMsg]      = useState<{ type: "success" | "error"; text: string } | null>(null);

  // ── Load user information from backend ────────────────────────────────────────────
  useEffect(() => {
    const stored = getStoredUser();
    if (stored) setUser(stored);
  }, []);

  const handleLogin = async () => {
    setLoginLoading(true); setLoginErr(null);
    try {
      const u = await loginUser(loginNim, loginPass);
      setUser(u);
    } catch (e: unknown) {
      setLoginErr(e instanceof Error ? e.message : "Login gagal.");
    } finally { setLoginLoading(false); }
  };

  const handleLogout = () => {
    clearToken();
    setUser(null);
    setVehicles([]);
  };

  // ── Load vehicles from backend ────────────────────────────────────────────
  const loadVehicles = useCallback(async () => {
    setVehiclesLoad(true); 
    setVehiclesErr(null);
    try {
      const data = await vehicleApi.list();
      setVehicles(data);
    } catch (e: unknown) {
      setVehiclesErr(e instanceof Error ? e.message : "Gagal memuat data kendaraan.");
    } finally {
      setVehiclesLoad(false);
    }
  }, []);

  useEffect(() => {
    const id = setInterval(loadVehicles, 20_000); // refresh tiap 5 detik
    return () => clearInterval(id);
  }, [loadVehicles]);

  // ── Plate input handler with auto-format ──────────────────────────────────
  const handlePlatChange = (raw: string) => {
    setNewPlat(formatPlateInput(raw));
    setNewPlatErr(null);
    setAddMsg(null);
  };

  // ── Add vehicle ────────────────────────────────────────────────────────────
  const handleAddVehicle = async () => {
    setAddMsg(null);

    // Client-side plate validation
    const validation = validatePlate(newPlat);
    if (!validation.valid) {
      setNewPlatErr(validation.error ?? "Format plat tidak valid.");
      return;
    }
    if (!newModel.trim()) {
      setAddMsg({ type: "error", text: "Merek / model kendaraan wajib diisi." });
      return;
    }

    setAddLoading(true);
    try {
      const result = await vehicleApi.add({
        plate_number: validation.normalized!,
        vehicle_type: newJenis,
        model:        newModel.trim(),
      }) as { message: string; plate_raw: string };
      setAddMsg({ type: "success", text: result.message });
      setNewPlat("");
      setNewModel("");
      setNewPlatErr(null);
      // Reload vehicle list from backend
      await loadVehicles();
    } catch (e: unknown) {
      setAddMsg({
        type:  "error",
        text:   e instanceof Error ? e.message : "Gagal mendaftarkan kendaraan.",
      });
    } finally {
      setAddLoading(false);
    }
  };

  // ── Delete vehicle callback ────────────────────────────────────────────────
  const handleDeleted = (plate: string) => {
    setVehicles((v) => v.filter((x) => x.plate_normalized !== plate));
  };

  if (!user) {
    return (
      <>
        <Navbar showSemester={false} minimal={true} />
        <div style={{
          background: "#f5f5f5", minHeight: "calc(100vh - 50px)",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            flex: 1, display: "flex", alignItems: "center",
            justifyContent: "center", padding: "40px 15px",
          }}>
            <div style={{ width: 320 }}>

              {/* Panel */}
              <div style={{
                border: "1px solid #ddd", borderRadius: 4,
                boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                background: "#fff",
              }}>
                {/* Header biru */}
                <div style={{
                  background: "#337ab7", color: "#fff",
                  padding: "10px 15px", borderRadius: "4px 4px 0 0",
                  fontSize: 15, fontWeight: 500,
                }}>
                  Non-ITB Account
                </div>

                <div style={{ padding: "15px" }}>
                  {/* Alert kuning */}
                  <div style={{
                    background: "#fcf8e3", border: "1px solid #faebcc",
                    borderRadius: 4, padding: "10px 14px", marginBottom: 15,
                  }}>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#8a6d3b" }}>
                      <li>13525001/mahasiswa1</li>
                      <li>13525002/mahasiswa2</li>
                      <li>13525003/mahasiswa3</li>
                    </ul>
                  </div>

                  {/* Input NIM */}
                  <input type="text" placeholder="User Name"
                    value={loginNim}
                    onChange={(e) => setLoginNim(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                    style={{
                      display: "block", width: "100%", padding: "6px 12px",
                      fontSize: 14, border: "1px solid #ccc", borderRadius: 4,
                      fontFamily: "'Roboto', sans-serif", marginBottom: 10,
                      boxSizing: "border-box", color: "#555",
                    }} autoFocus />

                  {/* Input Password */}
                  <input type="password" placeholder="Password"
                    value={loginPass}
                    onChange={(e) => setLoginPass(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                    style={{
                      display: "block", width: "100%", padding: "6px 12px",
                      fontSize: 14, border: "1px solid #ccc", borderRadius: 4,
                      fontFamily: "'Roboto', sans-serif", marginBottom: 10,
                      boxSizing: "border-box", color: "#555",
                    }} />

                  {loginErr && (
                    <div style={{
                      background: "#f2dede", border: "1px solid #ebccd1",
                      borderRadius: 4, padding: "8px 12px", fontSize: 13,
                      color: "#a94442", marginBottom: 10,
                    }}>
                      {loginErr}
                    </div>
                  )}

                  {/* Login button */}
                  <div style={{ textAlign: "center", marginTop: 6 }}>
                    <button type="button" onClick={handleLogin} disabled={loginLoading}
                      style={{
                        padding: "5px 20px", background: "#337ab7", color: "#fff",
                        border: "1px solid #2e6da4", borderRadius: 4, fontSize: 14,
                        cursor: loginLoading ? "not-allowed" : "pointer",
                        fontFamily: "'Roboto', sans-serif",
                        opacity: loginLoading ? 0.7 : 1,
                      }}>
                      {loginLoading ? "Masuk..." : "Login"}
                    </button>
                  </div>
                </div>
              </div>

            </div>
          </div>

          {/* Footer */}
          <div style={{ borderTop: "1px solid #ddd", padding: "16px 15px", textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 300, color: "#333" }}>Institut Teknologi Bandung</div>
            <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>Direktorat Pendidikan</div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navbar userName={user?.name ?? ""} showSemester={false} onLogout={handleLogout} />

      <Breadcrumb crumbs={[{ label: "SIX", href: "/" }, { label: "Parkir" }]} />

      <div className="page site-container">
        <h1>Parkir</h1>
        <p className="page-subtitle">ITB Jatinangor &mdash; Sistem Parkir ANPR</p>

        <div className="alert alert-info">
          ℹ&ensp;Sistem parkir <strong>ITB Jatinangor</strong> menggunakan{" "}
          <strong>ANPR (Automatic Number Plate Recognition)</strong>. Daftarkan plat nomor
          dan hubungkan e-wallet untuk autodebit otomatis saat keluar.
        </div>

        <TabMenu active={activeTab} onChange={setActiveTab} />

        {/* ══════════════════════════════════════════════════════════════════
            TAB 1 — Kendaraan Saya
        ══════════════════════════════════════════════════════════════════ */}
        <div className={`tab-content${activeTab === "kendaraan" ? " active" : ""}`}>

          {/* Kendaraan Terdaftar */}
          <div className="sec-title">Kendaraan Terdaftar</div>
          <div className="panel">
            <div className="panel-head">Daftar Kendaraan</div>
            <div className="panel-body" style={{ padding: "0 18px" }}>
              {vehiclesLoad && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
                  Memuat data kendaraan...
                </div>
              )}
              {vehiclesErr && (
                <div className="alert alert-warn" style={{ margin: "14px 0" }}>
                  {vehiclesErr}
                </div>
              )}
              {!vehiclesLoad && !vehiclesErr && vehicles.length === 0 && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "#aaa", fontSize: 13 }}>
                  Belum ada kendaraan terdaftar. Daftarkan kendaraan Anda di bawah.
                </div>
              )}
              {!vehiclesLoad && vehicles.map((v) => (
                <VehicleCard
                  key={v.plate_normalized}
                  vehicle={v}
                  onUpdated={loadVehicles}
                />
              ))}
            </div>
          </div>

          {/* Tambah Kendaraan Baru */}
          <div className="sec-title">Tambah Kendaraan Baru</div>
          <div className="card">
            <div className="form-row">

              {/* Plat Nomor with real-time validation */}
              <div className="fg">
                <label>Plat Nomor</label>
                <input
                  type="text"
                  placeholder="Contoh: D 1234 AB"
                  style={{
                    width: 160,
                    borderColor: newPlatErr ? "#c0392b" : undefined,
                    boxShadow: newPlatErr ? "0 0 0 2px rgba(192,57,43,0.15)" : undefined,
                  }}
                  value={newPlat}
                  onChange={(e) => handlePlatChange(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddVehicle()}
                  maxLength={12}
                  autoComplete="off"
                  spellCheck={false}
                />
                {newPlatErr && (
                  <span style={{ fontSize: 11, color: "#c0392b", marginTop: 2 }}>
                    {newPlatErr}
                  </span>
                )}
              </div>

              {/* Jenis */}
              <div className="fg">
                <label>Jenis</label>
                <select
                  style={{ width: 110 }}
                  value={newJenis}
                  onChange={(e) => setNewJenis(e.target.value as VehicleType)}
                >
                  <option value="motor">Motor</option>
                  <option value="mobil">Mobil</option>
                </select>
              </div>

              {/* Merek / Model */}
              <div className="fg">
                <label>Merek / Model</label>
                <input
                  type="text"
                  placeholder="Contoh: Honda Beat"
                  style={{ width: 175 }}
                  value={newModel}
                  onChange={(e) => { setNewModel(e.target.value); setAddMsg(null); }}
                  onKeyDown={(e) => e.key === "Enter" && handleAddVehicle()}
                  maxLength={60}
                />
              </div>

              {/* Submit button */}
              <div className="fg">
                <label style={{ visibility: "hidden" }}>x</label>
                <button
                  type="button"
                  className="btn btn-blue"
                  onClick={handleAddVehicle}
                  disabled={addLoading}
                  style={{ opacity: addLoading ? 0.7 : 1 }}
                >
                  {addLoading ? "Mendaftarkan..." : "+ Daftarkan"}
                </button>
              </div>
            </div>

            {/* Plate format guide */}
            <p className="hint">
              Format plat: 1-2 huruf area + 1-4 angka + 1-3 huruf. 
              Contoh: <strong>B 1234 ABC</strong>, <strong>D 4321 ITB</strong>, <strong>AB 12 CD</strong>.
              Setelah mendaftar, hubungkan e-wallet untuk autodebit otomatis.
            </p>

            {addMsg && (
              <div
                className={`alert ${addMsg.type === "success" ? "alert-success" : "alert-warn"}`}
                style={{ marginTop: 10, marginBottom: 0 }}
              >
                {addMsg.text}
              </div>
            )}
          </div>

          <div className="alert alert-info" style={{ marginTop: 2 }}>
            <strong>Verifikasi ANPR:</strong> Datang ke Pos Jaga Parkir dengan STNK untuk
            verifikasi manual. Kendaraan <em>Belum Aktif</em> tidak dapat menggunakan gerbang otomatis.
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════════
            TAB 2 — Status Parkir
        ══════════════════════════════════════════════════════════════════ */}
        <div className={`tab-content${activeTab === "status" ? " active" : ""}`}>
          <ParkingStatus totalVehicles={vehicles.length} onGateEvent={loadVehicles} />
        </div>

        {/* ══════════════════════════════════════════════════════════════════
            TAB 3 — Riwayat & Biaya
        ══════════════════════════════════════════════════════════════════ */}
        <div className={`tab-content${activeTab === "riwayat" ? " active" : ""}`}>
          <HistoryTable vehicles={vehicles} />
        </div>

        {/* ══════════════════════════════════════════════════════════════════
            TAB 4 — Informasi Tarif
        ══════════════════════════════════════════════════════════════════ */}
        <div className={`tab-content${activeTab === "tarif" ? " active" : ""}`}>
          <TarifInfo />
        </div>
      </div>
    </>
  );
}
