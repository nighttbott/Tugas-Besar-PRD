"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { vehicleApi, type AddVehiclePayload } from "@/lib/api";

export function useAddVehicle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AddVehiclePayload) => vehicleApi.add(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
  });
}
