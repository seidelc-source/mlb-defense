// src/stores/alignmentStore.ts
import { create } from 'zustand'
import type { AlignmentResponse } from '@/types'

interface AlignmentState {
  current: AlignmentResponse | null
  history: AlignmentResponse[]
  isLoading: boolean
  error: string | null
  setCurrent: (a: AlignmentResponse) => void
  setLoading: (v: boolean) => void
  setError: (e: string | null) => void
  addToHistory: (a: AlignmentResponse) => void
  clear: () => void
}

export const useAlignmentStore = create<AlignmentState>((set) => ({
  current: null,
  history: [],
  isLoading: false,
  error: null,
  setCurrent: (a) =>
    set((s) => ({ current: a, history: [a, ...s.history].slice(0, 20) })),
  setLoading: (v) => set({ isLoading: v }),
  setError: (e) => set({ error: e }),
  addToHistory: (a) =>
    set((s) => ({ history: [a, ...s.history].slice(0, 20) })),
  clear: () => set({ current: null, error: null }),
}))
