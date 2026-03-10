import { create } from 'zustand'
import type { ExecuteResponse } from '../api/types'

interface UiState {
  selectedNodeId: string | null
  setSelectedNodeId: (id: string | null) => void
  executeResult: ExecuteResponse | null
  setExecuteResult: (r: ExecuteResponse | null) => void
  isRunning: boolean
  setIsRunning: (v: boolean) => void
  captureConsole: boolean
  setCaptureConsole: (v: boolean) => void
  parallel: boolean
  setParallel: (v: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  executeResult: null,
  setExecuteResult: (r) => set({ executeResult: r }),
  isRunning: false,
  setIsRunning: (v) => set({ isRunning: v }),
  captureConsole: false,
  setCaptureConsole: (v) => set({ captureConsole: v }),
  parallel: false,
  setParallel: (v) => set({ parallel: v }),
}))
