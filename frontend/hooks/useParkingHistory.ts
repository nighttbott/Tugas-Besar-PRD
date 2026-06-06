"use client";

import { useQuery } from "@tanstack/react-query";
import { gateApi } from "@/lib/api";
import type { GateEvent } from "@/lib/api"; // History shares similar shape or we can use any

const POLL_INTERVAL_MS = 60_000; // 1 minute

export function useParkingHistory(limit = 50) {
  return useQuery({
    queryKey: ["parkingHistory", limit],
    queryFn: () => gateApi.getHistory(limit),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
