// src/hooks/useAlignment.ts
import { useMutation } from '@tanstack/react-query'
import { alignmentApi } from '@/api/alignmentApi'
import { useAlignmentStore } from '@/stores/alignmentStore'
import type { AlignmentRequest, AlignmentResponse } from '@/types'

export function useAlignment() {
  const { setCurrent, setLoading, setError } = useAlignmentStore()

  const mutation = useMutation<AlignmentResponse, Error, AlignmentRequest>({
    mutationFn: alignmentApi.recommend,
    onMutate: () => {
      setLoading(true)
      setError(null)
    },
    onSuccess: (data) => {
      setCurrent(data)
      setLoading(false)
    },
    onError: (err) => {
      setError(err.message)
      setLoading(false)
    },
  })

  return mutation
}
