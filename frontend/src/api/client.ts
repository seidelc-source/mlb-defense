// src/api/client.ts
import axios from 'axios'
import { IS_DEMO } from '@/lib/demo'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
})

// Static demo: resolve everything from prebaked fixtures, no backend.
// Lazy import so live builds tree-shake the adapter away entirely.
if (IS_DEMO) {
  apiClient.defaults.adapter = (config) =>
    import('@/demo/adapter').then(({ demoAdapter }) => demoAdapter(config))
}

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err.response?.data?.detail ?? err.message
    return Promise.reject(new Error(detail))
  }
)
