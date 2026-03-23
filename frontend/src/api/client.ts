import type { DagPayload, ExecuteResponse, ReplayPayload, SchemaResponse, SseEvent, SseProgressEvent, ValidateResponse } from './types'

const BASE = '/api'

export async function fetchSchema(): Promise<SchemaResponse> {
  const res = await fetch(`${BASE}/nodes/schema`)
  if (!res.ok) throw new Error(`Schema fetch failed: ${res.status}`)
  return res.json()
}

export async function validateDag(payload: DagPayload): Promise<ValidateResponse> {
  const res = await fetch(`${BASE}/dag/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Validation failed: ${res.status}`)
  return res.json()
}

export async function executeDag(payload: DagPayload): Promise<ExecuteResponse> {
  const res = await fetch(`${BASE}/dag/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Execution failed: ${res.status}`)
  return res.json()
}

export async function replayFailed(payload: ReplayPayload): Promise<ExecuteResponse> {
  const res = await fetch(`${BASE}/dag/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Replay failed: ${res.status}`)
  return res.json()
}

export async function executeStream(
  payload: DagPayload,
  onLine: (line: string) => void,
  onResult: (result: ExecuteResponse) => void,
  onProgress?: (evt: SseProgressEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/dag/execute/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok) throw new Error(`Stream execution failed: ${res.status}`)
  if (!res.body) throw new Error('Response body is null')

  const decoder = new TextDecoder()
  const reader = res.body.getReader()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const trimmed = frame.trim()
        if (!trimmed.startsWith('data: ')) continue
        let event: SseEvent
        try { event = JSON.parse(trimmed.slice(6)) } catch { continue }
        if (event.type === 'log') onLine(event.line)
        else if (event.type === 'result') onResult(event.payload)
        else if (event.type === 'progress' && onProgress) onProgress(event as SseProgressEvent)
        else if (event.type === 'error') throw new Error(event.message)
        else if (event.type === 'done') return
      }
    }
  } finally {
    reader.releaseLock()
  }
}
