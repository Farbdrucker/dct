import type { Edge, Node } from '@xyflow/react'
import { create } from 'zustand'
import type { CustomNodeData } from '../components/CustomNode'
import type { GroupNodeData } from '../components/GroupNode'
import type { ExecuteResponse, ExecutorMode, SseProgressEvent } from '../api/types'

type AnyNodeData = CustomNodeData | GroupNodeData

interface UiState {
  selectedNodeId: string | null
  setSelectedNodeId: (id: string | null) => void
  selectedNodeIds: string[]
  setSelectedNodeIds: (ids: string[]) => void
  executeResult: ExecuteResponse | null
  setExecuteResult: (r: ExecuteResponse | null) => void
  isRunning: boolean
  setIsRunning: (v: boolean) => void
  captureConsole: boolean
  setCaptureConsole: (v: boolean) => void
  executor: ExecutorMode
  setExecutor: (v: ExecutorMode) => void
  // clipboard
  clipboard: { nodes: Node<AnyNodeData>[]; edges: Edge[] } | null
  setClipboard: (c: { nodes: Node<AnyNodeData>[]; edges: Edge[] } | null) => void
  // progress
  progressMode: 'single' | 'batched' | null
  nodesCompleted: number
  nodesTotal: number | null
  rowsCompleted: number
  rowsPerSec: number | null
  startedAt: number | null
  lastElapsedMs: number | null
  startProgress: () => void
  setProgress: (p: SseProgressEvent) => void
  resetProgress: () => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  selectedNodeIds: [],
  setSelectedNodeIds: (ids) => set({ selectedNodeIds: ids }),
  executeResult: null,
  setExecuteResult: (r) => set({ executeResult: r }),
  isRunning: false,
  setIsRunning: (v) => set({ isRunning: v }),
  captureConsole: false,
  setCaptureConsole: (v) => set({ captureConsole: v }),
  executor: 'sequential',
  setExecutor: (v) => set({ executor: v }),
  // clipboard
  clipboard: null,
  setClipboard: (c) => set({ clipboard: c }),
  // progress
  progressMode: null,
  nodesCompleted: 0,
  nodesTotal: null,
  rowsCompleted: 0,
  rowsPerSec: null,
  startedAt: null,
  lastElapsedMs: null,
  startProgress: () => set({
    progressMode: null, nodesCompleted: 0, nodesTotal: null,
    rowsCompleted: 0, rowsPerSec: null, startedAt: Date.now(), lastElapsedMs: null,
  }),
  setProgress: (p) => set({
    progressMode: p.mode,
    nodesCompleted: p.nodes_completed ?? 0,
    nodesTotal: p.nodes_total ?? null,
    rowsCompleted: p.rows_completed ?? 0,
    rowsPerSec: p.rows_per_sec ?? null,
  }),
  resetProgress: () => set((state) => ({
    progressMode: null, nodesCompleted: 0, nodesTotal: null,
    rowsCompleted: 0, rowsPerSec: null,
    lastElapsedMs: state.startedAt ? Date.now() - state.startedAt : null,
    startedAt: null,
  })),
}))
