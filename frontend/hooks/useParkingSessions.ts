"use client";

import { useQuery } from "@tanstack/react-query";
import { vehicleApi, type SessionStats } from "@/lib/api";

export function useParkingSessions(nim?: string) {
  return useQuery({
    queryKey: ["parkingSessions", nim],
    queryFn: () => vehicleApi.sessions(nim),
    refetchInterval: 30 * 1000, // 30 detik
  });
}
