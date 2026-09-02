import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ingestApi, type IngestTriggerParams } from '@/api/ingestApi'
import { LoadingState, ErrorState } from '@/components/ui/StatusStates'
import { cn } from '@/lib/cn'
import type { IngestJobStatus } from '@/types'

interface JobEntry {
  jobId: string
  source: string
  triggeredAt: string
}

export function IngestDashboard() {
  const [jobs, setJobs] = useState<JobEntry[]>([])
  const [startDate, setStartDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [fieldingSeason, setFieldingSeason] = useState(2024)

  const queryClient = useQueryClient()

  const addJob = useCallback((jobId: string, source: string) => {
    setJobs((prev) => [
      { jobId, source, triggeredAt: new Date().toISOString() },
      ...prev,
    ])
  }, [])

  const statcastMutation = useMutation({
    mutationFn: (params: IngestTriggerParams) => ingestApi.triggerStatcast(params),
    onSuccess: (data) => {
      addJob(data.job_id, 'statcast')
      queryClient.invalidateQueries({ queryKey: ['ingest-job'] })
    },
  })

  const fieldingMutation = useMutation({
    mutationFn: (params: IngestTriggerParams) => ingestApi.triggerFielding(params),
    onSuccess: (data) => {
      addJob(data.job_id, 'fielding')
      queryClient.invalidateQueries({ queryKey: ['ingest-job'] })
    },
  })

  return (
    <div className="flex flex-col h-full p-6 overflow-y-auto">
      <h1 className="text-lg font-semibold text-[color:var(--ink)] mb-6">Data Ingest</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Statcast ingest card */}
        <div className="panel !p-5">
          <h2 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
            Statcast Pitch Data
          </h2>
          <p className="text-xs text-[color:var(--muted)] mb-4">
            Pull pitch-level data from Baseball Savant via pybaseball. Includes batted ball
            coordinates, pitch characteristics, and fielder positions.
          </p>
          <div className="flex gap-3 mb-4">
            <label className="text-xs text-[color:var(--muted)]">
              Start
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="block mt-0.5"
              />
            </label>
            <label className="text-xs text-[color:var(--muted)]">
              End
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="block mt-0.5"
              />
            </label>
          </div>
          <button
            onClick={() => statcastMutation.mutate({ start_date: startDate, end_date: endDate })}
            disabled={statcastMutation.isPending}
            className="btn-primary"
          >
            {statcastMutation.isPending ? 'Starting...' : 'Run Statcast Ingest'}
          </button>
          {statcastMutation.isError && (
            <ErrorState message={(statcastMutation.error as Error).message} />
          )}
        </div>

        {/* Fielding ingest card */}
        <div className="panel !p-5">
          <h2 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
            Fielding Leaderboards
          </h2>
          <p className="text-xs text-[color:var(--muted)] mb-4">
            Sync OAA, sprint speed, and fielding run value from Baseball Savant leaderboards.
            Merges into FieldingProfile by MLBAM ID.
          </p>
          <div className="mb-4">
            <label className="text-xs text-[color:var(--muted)]">
              Season
              <select
                value={fieldingSeason}
                onChange={(e) => setFieldingSeason(Number(e.target.value))}
                className="block mt-0.5"
              >
                {[2024, 2023, 2022, 2021].map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </label>
          </div>
          <button
            onClick={() => fieldingMutation.mutate({ season: fieldingSeason })}
            disabled={fieldingMutation.isPending}
            className="btn-primary"
          >
            {fieldingMutation.isPending ? 'Starting...' : 'Run Fielding Sync'}
          </button>
          {fieldingMutation.isError && (
            <ErrorState message={(fieldingMutation.error as Error).message} />
          )}
        </div>
      </div>

      {/* Job status list */}
      {jobs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
            Recent Jobs
          </h2>
          <div className="space-y-2">
            {jobs.map((job) => (
              <JobStatusRow key={job.jobId} jobId={job.jobId} source={job.source} triggeredAt={job.triggeredAt} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function JobStatusRow({ jobId, source, triggeredAt }: JobEntry) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['ingest-job', jobId],
    queryFn: () => ingestApi.getJobStatus(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'complete' || status === 'failed' ? false : 3000
    },
    staleTime: 1000,
  })

  if (isLoading) return <LoadingState message={`Checking ${source} job...`} />
  if (error) return <ErrorState message={(error as Error).message} />

  const status = data as IngestJobStatus

  return (
    <div className="panel !rounded-md !px-4 !py-3 flex items-center gap-4">
      <StatusBadge status={status.status} />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-[color:var(--ink)] font-medium">{source}</div>
        <div className="text-xs text-[color:var(--muted)] truncate">
          Job {jobId.slice(0, 8)} · started {new Date(triggeredAt).toLocaleTimeString()}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm text-[color:var(--ink)]">{status.records_processed} records</div>
        {status.errors.length > 0 && (
          <div className="text-xs text-[color:var(--danger)]">{status.errors.length} errors</div>
        )}
      </div>
      {status.status === 'running' && (
        <div className="w-4 h-4 border-2 border-[color:var(--line)] border-t-[color:var(--field)] rounded-full animate-spin shrink-0" />
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'px-2 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0',
        status === 'complete' && 'bg-[#e4f2e6] text-[color:var(--ok)]',
        status === 'running' && 'bg-[#e3edf6] text-[#1f596c]',
        status === 'pending' && 'bg-[#edf1ea] text-[color:var(--muted)]',
        status === 'failed' && 'bg-[#f6e3e3] text-[color:var(--danger)]',
      )}
    >
      {status}
    </span>
  )
}
