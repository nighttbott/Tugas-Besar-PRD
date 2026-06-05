"use client";

import { useQuery } from "@tanstack/react-query";
import { vehicleApi, type Vehicle } from "@/lib/api";

export function useVehicles(nim?: string) {
  return useQuery({
    queryKey: ["vehicles", nim],
    queryFn: () => vehicleApi.list(nim),
    refetchInterval: 20 * 1000, // 20 detik
  });
}
