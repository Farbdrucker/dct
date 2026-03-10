import type { ExecuteResponse } from '../api/types'

interface Props {
  result: ExecuteResponse | null
  isRunning: boolean
}

export function ResultPanel({ result, isRunning }: Props) {
  if (isRunning) {
    return (
      <div className="p-3 text-sm text-gray-400 animate-pulse">Running…</div>
    )
  }

  if (!result) return null

  if (!result.valid && result.errors && result.errors.length > 0) {
    return (
      <div className="p-3 space-y-1">
        <div className="text-red-500 font-semibold text-sm">Validation errors</div>
        {result.errors.map((e, i) => (
          <div key={i} className="text-xs text-red-400 bg-red-950 rounded px-2 py-1">
            <span className="font-mono">[{e.type}]</span> {e.message}
          </div>
        ))}
      </div>
    )
  }

  if (!result.success && result.error) {
    return (
      <div className="p-3 space-y-2">
        <div className="text-red-500 font-semibold text-sm">
          {result.error.exception_type}: {result.error.message}
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

  // Batched (source-driven)
  if (result.success && result.results.length > 0) {
    return (
      <div className="p-3 space-y-2">
        <div className="text-green-400 font-semibold text-sm">
          {result.results.length} results
        </div>
        <div className="space-y-0.5 max-h-48 overflow-y-auto">
          {result.results.map((r, i) => (
            <div key={i} className="text-xs font-mono text-gray-300 bg-gray-800 rounded px-2 py-0.5">
              [{i}] <span className="text-green-300">{JSON.stringify(r.value)}</span>
              <span className="text-gray-500"> :{r.value_type}</span>
            </div>
          ))}
        </div>
        <Trace trace={result.execution_trace} />
      </div>
    )
  }

  // Single-pass
  if (result.success && result.result) {
    return (
      <div className="p-3 space-y-2">
        <div className="text-green-400 font-semibold text-sm">
          Result: <span className="font-mono">{JSON.stringify(result.result.value)}</span>
          <span className="ml-2 text-gray-400 text-xs">({result.result.value_type})</span>
        </div>
        <Trace trace={result.execution_trace} />
      </div>
    )
  }

  return null
}

function Trace({ trace }: { trace: ExecuteResponse['execution_trace'] }) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400 font-semibold">Execution trace</div>
      {trace.map((step, i) => (
        <div key={i} className="text-xs font-mono text-gray-300 bg-gray-800 rounded px-2 py-0.5">
          {step.node_id} ({step.node_type}) → {JSON.stringify(step.value)}{' '}
          <span className="text-gray-500">:{step.value_type}</span>
        </div>
      ))}
    </div>
  )
}
