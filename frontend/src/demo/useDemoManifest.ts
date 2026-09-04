import { useQuery } from '@tanstack/react-query'
import { IS_DEMO } from '@/lib/demo'
import { loadDemoManifest } from '@/demo/adapter'

export function useDemoManifest() {
  return useQuery({
    queryKey: ['demo-manifest'],
    queryFn: loadDemoManifest,
    enabled: IS_DEMO,
    staleTime: Infinity,
  })
}
