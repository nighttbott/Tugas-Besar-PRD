/**
 * components/parking/HistoryTable.tsx
 * Riwayat & Biaya — fetches real history from GET /api/v1/gate/history.
 * Falls back to empty state if backend unavailable.
 */
"use client";

import { useState } from "react";
import type { Vehicle } from "@/lib/api";
import { useParkingHistory } from "@/hooks/useParkingHistory";

// Gate ID → readable location (mirrors backend GATE_LOCATIONS)
const GATE_LABELS: Record<string, string> = {
  G1:    "Parkir Mahasiswa",
  G2:    "Parkir Utama",
};

function gateLabel(gate_id: string, gate_location?: string): string {
  // Prefer gate_location from backend (already human-readable)
  if (gate_location) return gate_location;
  // Fallback to local map, then to gate_id itself
  return GATE_LABELS[gate_id] ?? gate_id;
}

export interface HistoryRecord {
  plate:          string;
  gate_id:        string;
  gate_location?: string;
  confidence:     number;
  entry_time:     string;
  exit_time?:     string;
  duration_secs?: number;
  fee?:           number;
  status:         "active" | "completed";
  is_guest?:      boolean;
}

interface HistoryTableProps {
  vehicles: Vehicle[];
}

const MONTHS = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"];
const NOW_MONTH = MONTHS[new Date().getMonth()];

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("id-ID", {
    weekday: "long", day: "numeric", month: "short", year: "numeric",
  });
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}
function fmtDur(secs?: number) {
  if (!secs) return "–";
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}j ${m}m` : `${m}m`;
}
function confColor(c: number) {
  return c >= 0.9 ? "#27ae60" : c >= 0.75 ? "#b45309" : "#c0392b";
}

export function HistoryTable({ vehicles }: HistoryTableProps) {
  const [filterPlat,  setFilterPlat]  = useState("all");
  const [filterBulan, setFilterBulan] = useState(NOW_MONTH);

  const { data: recordsData = [], isLoading: loading, error: errorObj } = useParkingHistory(200);
  const error = errorObj instanceof Error ? errorObj.message : null;
  
  const userPlates = new Set(vehicles.map((v) => v.plate_normalized));
  const records = (recordsData as HistoryRecord[]).filter((r) =>
    userPlates.size === 0 || userPlates.has(r.plate)
  );

  const filtered = records.filter((r) => {
    const platMatch = filterPlat === "all" || r.plate === filterPlat;
    const bulanIdx  = MONTHS.indexOf(filterBulan);
    const entryDate = new Date(r.entry_time);
    const bulanMatch = bulanIdx === -1 || entryDate.getMonth() === bulanIdx;
    const notGuest = !r.is_guest;
    return platMatch && bulanMatch;
  });

  const totalBiaya = filtered.reduce((s, r) => s + (r.fee ?? 0), 0);
  const uniquePlates = [...new Set(records.map((r) => r.plate))];

  return (
    <div>
      <div className="sec-title">Filter Riwayat</div>
      <div className="form-row" style={{ marginBottom: 14 }}>
        <div className="fg">
          <label>Plat Nomor</label>
          <select style={{ width: 165 }} value={filterPlat} onChange={(e) => setFilterPlat(e.target.value)}>
            <option value="all">Semua Kendaraan</option>
            {uniquePlates.map((p) => {
              const v = vehicles.find((vv) => vv.plate_normalized === p);
              return <option key={p} value={p}>{v?.plate_raw ?? p}</option>;
            })}
          </select>
        </div>
        <div className="fg">
          <label>Bulan</label>
          <select style={{ width: 145 }} value={filterBulan} onChange={(e) => setFilterBulan(e.target.value)}>
            {MONTHS.map((m) => (
              <option key={m} value={m}>{m} {new Date().getFullYear()}</option>
            ))}
          </select>
        </div>
        <div className="fg">
          <label style={{ visibility: "hidden" }}>x</label>
          <button type="button" className="btn btn-outline-blue"
            onClick={() => { setFilterPlat("all"); setFilterBulan(NOW_MONTH); }}>
            Reset Filter
          </button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          Riwayat Parkir
          <span className="badge badge-blue" style={{ marginLeft: 10, fontWeight: 400 }}>
            {filtered.length} entri
          </span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {loading ? (
            <div style={{ padding: "22px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
              Memuat riwayat...
            </div>
          ) : error ? (
            <div className="alert alert-warn" style={{ margin: 14 }}>{error}</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Tanggal / Waktu</th>
                  <th>Plat / ANPR</th>
                  <th>Lokasi</th>
                  <th>Durasi</th>
                  <th>Biaya</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "#aaa", padding: "22px 0" }}>
                      Tidak ada data untuk filter ini.
                    </td>
                  </tr>
                ) : (
                  filtered.map((r, i) => {
                    const v = vehicles.find((vv) => vv.plate_normalized === r.plate);
                    return (
                      <tr key={i}>
                        <td>
                          {fmtDate(r.entry_time)}
                          <br />
                          <span style={{ color: "#888", fontSize: 11.5 }}>
                            {fmtTime(r.entry_time)}
                            {r.exit_time && ` – ${fmtTime(r.exit_time)}`}
                          </span>
                        </td>
                        <td>
                          <span className="plate" style={{ fontSize: 10, padding: "2px 8px", letterSpacing: "1.5px" }}>
                            {v?.plate_raw ?? r.plate}
                          </span>
                          <br />
                          <span style={{ fontSize: 10.5, color: confColor(r.confidence) }}>
                            ANPR {(r.confidence * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td>
                          <div style={{ fontSize: 13 }}>
                            {gateLabel(r.gate_id, r.gate_location)}
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${r.status === "active" ? "badge-blue" : "badge-gray"}`}>
                            {fmtDur(r.duration_secs)}
                          </span>
                        </td>
                        <td style={{ fontWeight: 600 }}>
                          {r.fee ? `Rp${r.fee.toLocaleString("id-ID")}` : "–"}
                        </td>
                        <td>
                          {r.status === "active"
                            ? <span className="badge badge-blue">Parkir</span>
                            : <span className="badge badge-gray">Selesai</span>}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {filtered.length > 0 && (
        <div className="total-row">
          <span>Total Biaya — {filterBulan} {new Date().getFullYear()}</span>
          <strong>{totalBiaya > 0 ? `Rp${totalBiaya.toLocaleString("id-ID")}` : "–"}</strong>
        </div>
      )}
    </div>
  );
}
