"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

interface UpdateModelPayload {
  plate: string;
  model: string;
}

export function useUpdateVehicleModel(token: string | null) {
  const queryClient = useQueryClient();
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return useMutation({
    mutationFn: async ({ plate, model }: UpdateModelPayload) => {
      if (!token) throw new Error("Token tidak tersedia");

      const res = await fetch(`${apiBase}/api/v1/vehicles/${plate}/model`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ model }),
      });

      if (!res.ok) {
        throw new Error(`Gagal memperbarui model kendaraan: ${res.status}`);
      }
      
      return res.json();
    },
    onSuccess: () => {
      // Memicu refetch/invalidasi cache untuk daftar kendaraan dan sesi
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      queryClient.invalidateQueries({ queryKey: ["parkingSessions"] });
    },
  });
}
