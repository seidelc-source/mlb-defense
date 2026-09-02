// src/hooks/useSpray.ts
import { useQuery } from '@tanstack/react-query'
import { playerApi, type SprayParams } from '@/api/playerApi'

export function useSpray(playerId: string | null, params?: SprayParams) {
  return useQuery({
    queryKey: ['spray', playerId, params],
    queryFn: () => playerApi.getSpray(playerId!, params),
    enabled: !!playerId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export function usePlayer(playerId: string | null) {
  return useQuery({
    queryKey: ['player', playerId],
    queryFn: () => playerApi.get(playerId!),
    enabled: !!playerId,
    staleTime: 10 * 60 * 1000,
  })
}

// src/hooks/usePlayerRange.ts
export function usePlayerRange(
  playerId: string | null,
  position?: string,
  injuryActive = true
) {
  return useQuery({
    queryKey: ['range', playerId, position, injuryActive],
    queryFn: () => playerApi.getRange(playerId!, position, 2024, injuryActive),
    enabled: !!playerId,
    staleTime: 5 * 60 * 1000,
  })
}
