/**
 * components/parking/ParkingStatus.tsx
 * Status Parkir tab — reads LIVE data from backend.
 *
 * Data sources:
 *   • GET /api/v1/vehicles/sessions → stat grid + active session list
 *   • WebSocket /ws/gate-events     → real-time feed
 *
 * Stats shown (Image 4):
 *   - Kendaraan parkir aktif (from active_count)
 *   - Durasi parkir saat ini (live elapsed of first active session)
 *   - Estimasi biaya         (from est_fee of first active session)
 *   - Kendaraan terdaftar    (from total_vehicles)
 *
 * "Kendaraan Sedang Parkir" renders one row per active session from DB.
 */
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { type ActiveSession } from "@/lib/api";
import { LiveGateEvent } from "@/components/ui/LiveGateEvent";
import { useParkingSessions } from "@/hooks/useParkingSessions";

interface ParkingStatusProps {
  totalVehicles: number;  // passed from parent (vehicle list count)
  onGateEvent?: () => void;
}

function calcLiveDuration(entryTs: number) {
  const elapsed = Math.floor(Date.now() / 1000 - entryTs);
  const h = Math.floor(elapsed / 3600);
  const m = Math.floor((elapsed % 3600) / 60);
  const jam = Math.ceil(elapsed / 3600) || 1;
  const fee = Math.min(1000 + (jam - 1) * 1000, 2000); // motor default
  return {
    label:  `${h}j ${m}m`,
    estFee: `Rp${fee.toLocaleString("id-ID")}`,
    estFeeNum: fee,
  };
}

const GATE_LABELS: Record<string, string> = {
  G1:    "Parkir Mahasiswa",
  G2:    "Pintu Gerbang Utama",
  EXIT1: "Gerbang Keluar 1",
  EXIT2: "Gerbang Keluar 2",
};

function formatEntryTime(iso: string) {
  const d = new Date(iso);
  const time = d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  const date = d.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return { time: `${time} WIB`, date };
}

export function ParkingStatus({ totalVehicles, onGateEvent }: ParkingStatusProps) {
  const { data: stats, isLoading: loading, error: errorObj, refetch: fetchStats } = useParkingSessions();
  const error = errorObj instanceof Error ? errorObj.message : null;

  const [liveDur, setLiveDur]   = useState<{ label: string; estFee: string; estFeeNum: number } | null>(null);
  const timerRef                = useRef<ReturnType<typeof setInterval> | null>(null);

  const today = new Date().toLocaleDateString("id-ID", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  // ── Live duration ticker for active sessions ───────────────────────────────
  useEffect(() => {
    const first = stats?.active_sessions?.[0];
    if (!first) { setLiveDur(null); return; }

    const tick = () => setLiveDur(calcLiveDuration(first.entry_ts));
    tick();
    timerRef.current = setInterval(tick, 30_000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [stats]);

  // When a new gate event fires, refresh stats immediately
  const handleGateEvent = useCallback(() => {
    setTimeout(fetchStats, 1000); // 1s delay so Redis is updated
    if (onGateEvent) setTimeout(onGateEvent, 1500);
  }, [fetchStats, onGateEvent]);

  const firstSession: ActiveSession | null = stats?.active_sessions?.[0] ?? null;
  const activeCount  = stats?.active_count ?? 0;
  const totalReg     = stats?.total_vehicles ?? totalVehicles;

  const entryFmt = firstSession ? formatEntryTime(firstSession.entry_time) : null;
  const ewalletLabel = firstSession?.primary_ewallet
    ? `Autodebit ${firstSession.primary_ewallet.provider}`
    : "Tidak ada e-wallet";
  const ewalletSaldo = firstSession?.primary_ewallet
    ? `Saldo: Rp${firstSession.primary_ewallet.balance.toLocaleString("id-ID")}`
    : "–";

  return (
    <div>
      {/* Real-time gate event feed */}
      <LiveGateEvent onEvent={handleGateEvent} />

      {/* ── Ringkasan Hari Ini ── */}
      <div className="sec-title">Ringkasan Hari Ini</div>
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head">Statistik Parkir — {today}</div>
        <div className="panel-body">
          {loading ? (
            <div style={{ textAlign: "center", padding: "20px 0", color: "#888", fontSize: 13 }}>
              Memuat data...
            </div>
          ) : error ? (
            <div className="alert alert-warn" style={{ margin: 0 }}>{error}</div>
          ) : (
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-num">{activeCount}</div>
                <div className="stat-lbl">Kendaraan parkir aktif</div>
              </div>
              <div className="stat-box">
                <div className="stat-num">{liveDur?.label ?? (activeCount === 0 ? "–" : "0j 0m")}</div>
                <div className="stat-lbl">Durasi parkir saat ini</div>
              </div>
              <div className="stat-box">
                <div className="stat-num">{liveDur?.estFee ?? "–"}</div>
                <div className="stat-lbl">Estimasi biaya</div>
              </div>
              <div className="stat-box">
                <div className="stat-num">{totalReg}</div>
                <div className="stat-lbl">Kendaraan terdaftar</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Kendaraan Sedang Parkir ── */}
      <div className="sec-title">Kendaraan Sedang Parkir</div>
      {loading ? null : !firstSession ? (
        <div className="card" style={{ textAlign: "center", color: "#aaa", padding: "22px 0", fontSize: 13 }}>
          Tidak ada kendaraan yang sedang parkir saat ini.
        </div>
      ) : (
        <>
          {stats!.active_sessions.map((session) => {
            const fmt = formatEntryTime(session.entry_time);
            const dur = calcLiveDuration(session.entry_ts);
            const ew  = session.primary_ewallet;
            return (
              <div className="panel" key={session.plate_normalized} style={{ marginBottom: 18 }}>
                <div className="panel-head">Sesi Aktif</div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <div className="status-big" style={{ marginBottom: 0, border: "none", borderRadius: 0 }}>
                    {/* Plat Nomor cell */}
                    <div className="status-cell active-cell">
                      <div className="lbl">Plat Nomor</div>
                      <div className="val">
                        <span className="plate" style={{ fontSize: 11, padding: "3px 10px", letterSpacing: "2px" }}>
                          {session.plate_raw}
                        </span>
                      </div>
                      <div className="sub">
                        {session.model} &bull; {session.vehicle_type === "motor" ? "Motor" : "Mobil"}
                      </div>
                    </div>
                    {/* Lokasi Gerbang */}
                    <div className="status-cell">
                      <div className="lbl">Lokasi Gerbang</div>
                      <div className="val">{GATE_LABELS[session.gate_id] ?? session.gate_id}</div>
                      <div className="sub">Kampus ITB Jatinangor</div>
                    </div>
                    {/* Waktu Masuk */}
                    <div className="status-cell">
                      <div className="lbl">Waktu Masuk</div>
                      <div className="val">{fmt.time}</div>
                      <div className="sub">{fmt.date}</div>
                    </div>
                    {/* Durasi */}
                    <div className="status-cell">
                      <div className="lbl">Durasi</div>
                      <div className="val">{dur.label}</div>
                      <div className="sub">Estimasi: <strong>{dur.estFee}</strong></div>
                    </div>
                    {/* Metode Keluar */}
                    <div className="status-cell">
                      <div className="lbl">Metode Keluar</div>
                      <div className="val" style={{ fontSize: 13 }}>
                        {ew ? `Autodebit ${ew.provider}` : "Manual / QRIS"}
                      </div>
                      <div className="sub">
                        {ew ? `Saldo: Rp${ew.balance.toLocaleString("id-ID")}` : "Tidak ada e-wallet"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </>
      )}

      {/* ── Status Gerbang ── */}
      <div className="sec-title">Status Gerbang</div>
      <GateStatusChips />
    </div>
  );
}

function GateStatusChips() {
  const [gates, setGates] = useState<string[]>([]);
  const [lastUpdate, setLastUpdate] = useState<string>("");

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/gate/status`
      );
      const d = await res.json();
      setGates(d.online_gates ?? []);
      setLastUpdate(new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    } catch { /* backend offline — keep last known state */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Poll every 5 seconds — ESP32 WebSocket connects instantly when script starts
    const id = setInterval(fetchStatus, 5_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const allGates = [
    { id: "G1",    label: "Gerbang Masuk 1 — Parkir Mahasiswa" },
    { id: "G2",    label: "Gerbang Masuk 2 — Pintu Utama"      },
    { id: "EXIT1", label: "Gerbang Keluar 1"                    },
  ];

  return (
    <div>
      <div className="gate-info">
        {allGates.map((g) => {
          const online = gates.includes(g.id);
          return (
            <div key={g.id} className="gate-chip">
              <strong>{g.id}</strong>
              {g.label}
              <span
                className={`badge ${online ? "badge-green" : "badge-red"}`}
                style={{ marginLeft: 8 }}
              >
                {online ? "● Online" : "○ Offline"}
              </span>
            </div>
          );
        })}
      </div>
      {lastUpdate && (
        <p style={{ fontSize: 11, color: "#aaa", marginTop: 6, marginBottom: 0 }}>
          Diperbarui otomatis setiap 5 detik · terakhir: {lastUpdate}
        </p>
      )}
      <div className="alert alert-info" style={{ marginTop: 12, fontSize: 12 }}>
        <strong>Cara kerja Status Gerbang:</strong> Setiap ESP32 yang terpasang di gerbang
        menghubungkan diri ke backend via WebSocket saat menyala. Status <strong>Online</strong>{" "}
        berarti ESP32 terhubung dan siap menerima perintah buka gerbang dari ANPR.{" "}
        <strong>Offline</strong> berarti ESP32 belum menyala atau koneksi terputus.
      </div>
    </div>
  );
}
