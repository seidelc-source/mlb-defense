import { apiClient } from './client'
import type { IngestJobStatus } from '@/types'

export interface IngestTriggerParams {
  start_date?: string
  end_date?: string
  season?: number
}

export interface IngestTriggerResponse {
  job_id: string
  status: string
  message: string
}

export const ingestApi = {
  triggerStatcast: async (params: IngestTriggerParams): Promise<IngestTriggerResponse> => {
    const { data } = await apiClient.post('/ingest/statcast', null, { params })
    return data
  },

  triggerFielding: async (params: IngestTriggerParams): Promise<IngestTriggerResponse> => {
    const { data } = await apiClient.post('/ingest/fielding', null, { params })
    return data
  },

  getJobStatus: async (jobId: string): Promise<IngestJobStatus> => {
    const { data } = await apiClient.get(`/ingest/jobs/${jobId}`)
    return data
  },
}
