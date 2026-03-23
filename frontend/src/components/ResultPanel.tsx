import { useEffect, useState } from 'react'
import type { ExecuteResponse, ExecutionResult, FailureReport } from '../api/types'
import { useUiStore } from '../store/uiStore'

interface Props {
  result: ExecuteResponse | null
  isRunning: boolean
  onReplay?: (report: FailureReport) => void
}

function formatDuration(s: number): string {
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function ElapsedBadge() {
  const lastElapsedMs = useUiStore((s) => s.lastElapsedMs)
  if (!lastElapsedMs) return null
  const s = lastElapsedMs / 1000
  const label = s < 60
    ? `${s.toFixed(s < 10 ? 2 : 1)}s`
    : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return (
    <span className="text-xs text-gray-500 ml-auto shrink-0">{label}</span>
  )
}

const indeterminateStyle: React.CSSProperties = {
  width: '35%',
  animation: 'indeterminate-bar 1.4s ease-in-out infinite',
}

function ProgressWidget() {
  const { progressMode, nodesCompleted, nodesTotal, rowsCompleted, rowsPerSec, startedAt } = useUiStore()
  const [elapsedMs, setElapsedMs] = useState(0)

  useEffect(() => {
    if (!startedAt) return
    setElapsedMs(0)
    const id = setInterval(() => setElapsedMs(Date.now() - startedAt), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  const pct = progressMode === 'single' && nodesTotal ? nodesCompleted / nodesTotal : null
  const elapsedSec = Math.floor(elapsedMs / 1000)
  const etaSec = pct && pct > 0.05 ? Math.round(elapsedSec * (1 - pct) / pct) : null

  return (
    <div className="p-3 space-y-2">
      <div className="flex items-center gap-2">
        <svg className="animate-spin h-4 w-4 text-green-400 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-sm text-gray-400">Running…</span>
        <span className="text-xs text-gray-500 ml-auto">{formatDuration(elapsedSec)}</span>
      </div>

      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        {pct !== null
          ? <div
              className="h-full bg-green-500 rounded-full transition-all duration-300"
              style={{ width: `${pct * 100}%` }}
            />
          : <div className="h-full bg-green-500 rounded-full" style={indeterminateStyle} />
        }
      </div>

      <div className="text-xs text-gray-500">
        {progressMode === 'single' && nodesTotal
          ? `Node ${nodesCompleted} / ${nodesTotal}${etaSec !== null ? `  ·  ETA ~${formatDuration(etaSec)}` : ''}`
          : progressMode === 'batched'
          ? `${rowsCompleted} rows${rowsPerSec !== null ? `  ·  ${rowsPerSec} rows/sec` : ''}`
          : null
        }
      </div>
    </div>
  )
}

export function ResultPanel({ result, isRunning, onReplay }: Props) {
  if (isRunning) {
    return <ProgressWidget />
  }

  if (!result) return null

  if (!result.valid && result.errors && result.errors.length > 0) {
    return (
      <div className="p-3 space-y-1">
        <div className="flex items-center text-red-500 font-semibold text-sm">Validation errors<ElapsedBadge /></div>
        {result.errors.map((e, i) => (
          <div key={i} className="text-xs text-red-400 bg-red-950 rounded px-2 py-1">
            <span className="font-mono">[{e.type}]</span> {e.message}
          </div>
        ))}
      </div>
    )
  }

  // Complete failure (no row-level report — single-pass error or pre-execution failure)
  if (!result.success && result.error && !result.failure_report) {
    return (
      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2 text-red-500 font-semibold text-sm">
          <span>{result.error.exception_type}: {result.error.message}</span><ElapsedBadge />
        </div>
        <pre className="text-xs text-red-300 bg-red-950 rounded p-2 overflow-auto max-h-40">
          {result.error.traceback}
        </pre>
        {result.execution_trace.length > 0 && (
          <Trace trace={result.execution_trace} />
        )}
      </div>
    )
  }

  // Batched (source-driven) — partial or full success
  // Also fires when all rows hit sinks (results=[] but row_results is populated)
  if (result.results.length > 0 || result.failure_report || (result.row_results && result.row_results.length > 0)) {
    const total = result.row_results?.length ?? result.results.length
    const succeeded = result.row_results
      ? result.row_results.filter((r) => r.success).length
      : result.results.length
    return (
      <div className="p-3 space-y-2">
        <div className={`flex items-center font-semibold text-sm ${result.success ? 'text-green-400' : 'text-yellow-400'}`}>
          {succeeded}/{total} rows succeeded<ElapsedBadge />
        </div>
        {result.results.length > 0 && (
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {result.results.map((r, i) => (
              <div key={i} className="text-xs font-mono text-gray-300 bg-gray-800 rounded px-2 py-0.5">
                [{i}] <span className="text-green-300">{JSON.stringify(r.value)}</span>
                <span className="text-gray-500"> :{r.value_type}</span>
              </div>
            ))}
          </div>
        )}
        {result.failure_report && result.failure_report.failed_rows > 0 && (
          <FailureReportPanel report={result.failure_report} onReplay={onReplay} />
        )}
        {result.execution_trace.length > 0 && (
          <Trace trace={result.execution_trace} />
        )}
      </div>
    )
  }

  // Single-pass
  if (result.result) {
    return (
      <div className="p-3 space-y-2">
        {result.success ? (
          <div className="flex items-center gap-1 text-green-400 font-semibold text-sm">
            <span>Result: <span className="font-mono">{JSON.stringify(result.result.value)}</span></span>
            <span className="text-gray-400 text-xs font-normal">({result.result.value_type})</span>
            <ElapsedBadge />
          </div>
        ) : (
          <div className="text-red-500 font-semibold text-sm">Execution failed</div>
        )}
        <Trace trace={result.execution_trace} />
      </div>
    )
  }

  // Fallback: execution ran but produced no displayable result (e.g. sink-only single-pass)
  if (result.success) {
    return (
      <div className="p-3">
        <div className="flex items-center text-green-400 font-semibold text-sm">Execution succeeded<ElapsedBadge /></div>
        {result.execution_trace.length > 0 && <Trace trace={result.execution_trace} />}
      </div>
    )
  }

  return null
}

function Trace({ trace }: { trace: ExecutionResult[] }) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400 font-semibold">Execution trace</div>
      {trace.map((step, i) => (
        <div
          key={i}
          className={`text-xs font-mono rounded px-2 py-0.5 ${
            step.error && !step.skipped
              ? 'text-red-300 bg-red-950'
              : step.skipped
              ? 'text-yellow-400 bg-yellow-950'
              : 'text-gray-300 bg-gray-800'
          }`}
        >
          {step.node_id} ({step.node_type}){' '}
          {step.error && !step.skipped
            ? `→ ERROR: ${step.error.exception_type}: ${step.error.message}`
            : step.skipped
            ? '→ [skipped]'
            : <>→ {JSON.stringify(step.value)} <span className="text-gray-500">:{step.value_type}</span></>
          }
        </div>
      ))}
    </div>
  )
}

function FailureReportPanel({ report, onReplay }: { report: FailureReport; onReplay?: (r: FailureReport) => void }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <div className="text-xs text-red-400 font-semibold">
          {report.failed_rows} failed row{report.failed_rows !== 1 ? 's' : ''}
        </div>
        {onReplay && (
          <button
            onClick={() => onReplay(report)}
            className="ml-auto px-2 py-0.5 text-xs rounded bg-yellow-700 hover:bg-yellow-600 text-white transition-colors"
          >
            Replay Failed
          </button>
        )}
      </div>
      <div className="space-y-0.5 max-h-40 overflow-y-auto">
        {report.failed_items.map((row) => (
          <div key={row.row_index} className="text-xs bg-red-950 rounded px-2 py-1">
            <span className="text-gray-400">Row {row.row_index}</span>
            {row.error && (
              <span className="text-red-300 ml-2">
                {row.error.node_type}: {row.error.exception_type}: {row.error.message}
              </span>
            )}
            <div className="text-gray-500 mt-0.5 font-mono">
              {Object.entries(row.source_values)
                .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                .join(', ')}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
