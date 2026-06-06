"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { vehicleApi } from "@/lib/api";

export function useDeleteVehicle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (plate: string) => vehicleApi.delete(plate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
  });
}
