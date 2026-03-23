// TypeScript types mirroring the Python JSON contract

export interface ConfigField {
  name: string
  type: string
  type_set: string[]
  default: unknown | null
  required: boolean
  json_schema: Record<string, unknown>
}

export interface Port {
  name: string
  type: string
  type_set: string[]
}

export interface NodeSchema {
  class_name: string
  kind: 'transition' | 'source' | 'sink'
  description?: string | null
  config_fields: ConfigField[]
  input_ports: Port[]
  output_port: Port | null
}

export interface SchemaResponse {
  schema_version: string
  nodes: NodeSchema[]
}

// DAG payload
export interface NodeData {
  config: Record<string, unknown>
  constants: Record<string, unknown>
}

export interface DagNode {
  id: string
  type: string
  data: NodeData
}

export interface DagEdge {
  id: string
  source: string
  source_handle: string
  target: string
  target_handle: string
}

export type ExecutorMode = 'sequential' | 'parallel' | 'dask'

export interface DagPayload {
  nodes: DagNode[]
  edges: DagEdge[]
  capture_logs?: boolean
  executor?: ExecutorMode
}

// Validation response
export interface ValidationError {
  type: string
  edge_id?: string
  node_id?: string
  source_node?: string
  target_node?: string
  target_handle?: string
  source_type_set?: string[]
  target_type_set?: string[]
  message: string
}

export interface ValidateResponse {
  valid: boolean
  errors: ValidationError[]
}

// Execution response
export interface ExecutionResult {
  node_id: string
  node_type: string
  value: unknown
  value_type: string
  error?: ExecutionError   // set if this node failed
  skipped?: boolean        // true if bypassed due to upstream error
}

export interface ExecutionError {
  node_id: string
  node_type: string
  exception_type: string
  message: string
  traceback: string
}

export interface RowResult {
  row_index: number
  success: boolean
  result?: ExecutionResult
  error?: ExecutionError
  trace?: ExecutionResult[]          // per-row trace (failed rows only)
  source_values: Record<string, unknown>
}

export interface FailureReport {
  total_rows: number
  succeeded_rows: number
  failed_rows: number
  failed_items: RowResult[]
}

export interface ExecuteResponse {
  success: boolean
  result?: ExecutionResult          // single-pass
  results: ExecutionResult[]        // successful row finals (source-driven)
  execution_trace: ExecutionResult[]
  error?: ExecutionError
  valid?: boolean
  errors?: ValidationError[]
  console_output?: string[]
  row_results?: RowResult[]
  failure_report?: FailureReport
}

export interface ReplayPayload {
  nodes: DagNode[]
  edges: DagEdge[]
  capture_logs?: boolean
  executor?: 'sequential' | 'parallel'
  failed_items: RowResult[]
}

export interface SseLogEvent      { type: 'log';      line: string }
export interface SseResultEvent   { type: 'result';   payload: ExecuteResponse }
export interface SseErrorEvent    { type: 'error';    message: string }
export interface SseDoneEvent     { type: 'done' }
export interface SseProgressEvent {
  type: 'progress'
  mode: 'single' | 'batched'
  nodes_completed: number | null
  nodes_total: number | null
  rows_completed: number | null
  rows_per_sec: number | null
  node_id: string | null
  node_type: string | null
}
export type SseEvent = SseLogEvent | SseResultEvent | SseErrorEvent | SseDoneEvent | SseProgressEvent
