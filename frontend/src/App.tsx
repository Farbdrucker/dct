import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Node } from '@xyflow/react'
import { executeStream, replayFailed } from './api/client'
import type { FailureReport, NodeSchema } from './api/types'
import { Canvas } from './components/Canvas'
import { ConsolePanel } from './components/ConsolePanel'
import { NodeLibrary } from './components/NodeLibrary'
import { PropertiesPanel } from './components/PropertiesPanel'
import { ResultPanel } from './components/ResultPanel'
import type { CustomNodeData } from './components/CustomNode'
import { isGroupNodeData } from './components/GroupNode'
import { useDagStore } from './hooks/useDag'
import { useSchema } from './hooks/useSchema'
import { useUiStore } from './store/uiStore'
import { decodeDagFromHash, encodeDagToHash, exportDagToJson, parseDagFromJson, serializeDag } from './utils/dagSerializer'

const queryClient = new QueryClient()

function DctApp() {
  const { data: schemaData, isLoading, isError, error } = useSchema()
  const schemas = schemaData?.nodes ?? []
  const { nodes, edges, addNode, setNodes, setEdges, groupNodes, ungroupNodes } = useDagStore()
  const { selectedNodeId, setSelectedNodeId, selectedNodeIds, setSelectedNodeIds, executeResult, setExecuteResult, isRunning, setIsRunning, captureConsole, setCaptureConsole, executor, setExecutor, startProgress, setProgress, resetProgress } =
    useUiStore()

  const [consoleLines, setConsoleLines] = useState<string[]>([])
  const [runError, setRunError] = useState<string | null>(null)

  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  const selectedNodes = nodes.filter((n) => selectedNodeIds.includes(n.id))
  const canGroup =
    selectedNodeIds.length >= 2 &&
    selectedNodes.every((n) => !isGroupNodeData(n.data) && !n.hidden)
  const canUngroup =
    selectedNodeIds.length === 1 && isGroupNodeData(selectedNodes[0]?.data)

  const handleGroup = useCallback(() => {
    const label = prompt('Group label:', 'Group') ?? 'Group'
    if (label.trim()) groupNodes(selectedNodeIds, label.trim())
  }, [selectedNodeIds, groupNodes])

  const handleUngroup = useCallback(() => {
    ungroupNodes(selectedNodeIds[0])
  }, [selectedNodeIds, ungroupNodes])

  const handleAddNode = useCallback(
    (schema: NodeSchema) => {
      const id = `${schema.class_name}-${Date.now()}`
      const newNode: Node<CustomNodeData> = {
        id,
        type: 'custom',
        position: { x: 200 + Math.random() * 100, y: 100 + Math.random() * 100 },
        data: {
          schemaName: schema.class_name,
          schema,
          config: {},
          constants: {},
        },
      }
      addNode(newNode)
      setSelectedNodeId(id)
    },
    [addNode, setSelectedNodeId],
  )

  const restoredFromHash = useRef(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Effect A: restore DAG from URL hash once schemas are available (runs once)
  useEffect(() => {
    if (restoredFromHash.current || schemas.length === 0) return
    restoredFromHash.current = true
    const raw = window.location.hash.slice(1)
    if (!raw) return
    const json = decodeDagFromHash(raw)
    if (!json) {
      console.warn('[dct] Invalid URL hash — ignoring')
      window.location.hash = ''
      return
    }
    try {
      const schemasByName = Object.fromEntries(schemas.map((s) => [s.class_name, s]))
      const { nodes: newNodes, edges: newEdges } = parseDagFromJson(json, schemasByName)
      setNodes(newNodes)
      setEdges(newEdges)
    } catch (err) {
      console.warn('[dct] Failed to restore DAG from URL:', err)
      window.location.hash = ''
    }
  }, [schemas, setNodes, setEdges])

  // Effect B: sync DAG state to URL hash (debounced 300 ms)
  useEffect(() => {
    if (!restoredFromHash.current) return
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (nodes.length === 0) {
        window.location.hash = ''
      } else {
        window.location.hash = encodeDagToHash(nodes, edges)
      }
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [nodes, edges])

  const importRef = useRef<HTMLInputElement>(null)

  const handleExport = useCallback(() => {
    const json = exportDagToJson(nodes, edges)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'dag.json'
    a.click()
    URL.revokeObjectURL(url)
  }, [nodes, edges])

  const handleExportForRun = useCallback(() => {
    const payload = serializeDag(nodes, edges)
    const json = JSON.stringify(payload, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'dag_payload.json'
    a.click()
    URL.revokeObjectURL(url)
  }, [nodes, edges])

  const handleImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (ev) => {
        try {
          const schemasByName = Object.fromEntries(schemas.map((s) => [s.class_name, s]))
          const { nodes: newNodes, edges: newEdges } = parseDagFromJson(
            ev.target!.result as string,
            schemasByName,
          )
          setNodes(newNodes)
          setEdges(newEdges)
        } catch (err) {
          alert(`Import failed: ${err}`)
        }
        e.target.value = ''
      }
      reader.readAsText(file)
    },
    [schemas, setNodes, setEdges],
  )

  const handleRun = useCallback(async () => {
    setIsRunning(true)
    setExecuteResult(null)
    setConsoleLines([])
    setRunError(null)
    startProgress()
    try {
      const payload = { ...serializeDag(nodes, edges), capture_logs: captureConsole, executor }
      await executeStream(
        payload,
        captureConsole ? (line) => setConsoleLines((prev) => [...prev, line]) : () => {},
        (result) => setExecuteResult(result),
        (evt) => setProgress(evt),
      )
    } catch (err) {
      console.error(err)
      setRunError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsRunning(false)
      resetProgress()
    }
  }, [nodes, edges, setIsRunning, setExecuteResult, captureConsole, executor, startProgress, setProgress, resetProgress])

  const handleReplay = useCallback(async (failureReport: FailureReport) => {
    setIsRunning(true)
    setExecuteResult(null)
    setConsoleLines([])
    setRunError(null)
    try {
      const dag = serializeDag(nodes, edges)
      const result = await replayFailed({
        nodes: dag.nodes,
        edges: dag.edges,
        capture_logs: true,
        executor: executor === 'dask' ? 'sequential' : executor,
        failed_items: failureReport.failed_items,
      })
      setExecuteResult(result)
      if (result.console_output && result.console_output.length > 0) {
        setConsoleLines(result.console_output)
      }
    } catch (err) {
      console.error(err)
      setRunError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsRunning(false)
    }
  }, [nodes, edges, setIsRunning, setExecuteResult, captureConsole, executor])

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        Loading schema…
      </div>
    )
  }

  if (isError) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 text-red-400">
        <span className="font-semibold">Failed to load schema from backend</span>
        <span className="text-xs text-gray-500">{String(error)}</span>
        <span className="text-xs text-gray-500">Is the API server running? <code>uv run uvicorn dct.api.app:app --reload</code></span>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-gray-950 text-white">
      {/* Topbar */}
      <div className="flex items-center px-4 py-2 bg-gray-900 border-b border-gray-700 gap-4">
        <span className="font-bold text-lg tracking-tight">DCT</span>
        <span className="text-gray-500 text-xs font-mono">{schemaData?.schema_version}</span>
        <div className="ml-auto flex gap-2">
          <input ref={importRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
          <button
            onClick={() => importRef.current?.click()}
            className="px-3 py-1.5 text-sm rounded bg-gray-700 hover:bg-gray-600 transition-colors"
          >
            Import
          </button>
          <button
            onClick={handleExport}
            disabled={nodes.length === 0}
            className="px-3 py-1.5 text-sm rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Export
          </button>
          <button
            onClick={handleExportForRun}
            disabled={nodes.length === 0}
            className="px-3 py-1.5 text-sm rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Export for Run
          </button>
          <button
            onClick={handleGroup}
            disabled={!canGroup}
            className="px-3 py-1.5 text-sm rounded bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Group
          </button>
          <button
            onClick={handleUngroup}
            disabled={!canUngroup}
            className="px-3 py-1.5 text-sm rounded bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Ungroup
          </button>
          <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
            <input type="checkbox" checked={captureConsole} onChange={e => setCaptureConsole(e.target.checked)} className="accent-green-500" />
            Console
          </label>
          <select
            value={executor}
            onChange={e => setExecutor(e.target.value as typeof executor)}
            className="px-2 py-1.5 text-sm rounded bg-gray-700 text-gray-200 border border-gray-600 cursor-pointer"
          >
            <option value="sequential">Sequential</option>
            <option value="parallel">Parallel</option>
            <option value="dask">Dask</option>
          </select>
          <button
            onClick={handleRun}
            disabled={isRunning || nodes.length === 0}
            className="px-4 py-1.5 text-sm font-semibold rounded bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        <div className="flex-1 flex overflow-hidden min-h-0">
          <NodeLibrary schemas={schemas} onAdd={handleAddNode} />

          <div
            className="flex-1 relative"
            onClick={(e) => {
              if ((e.target as HTMLElement).closest('.react-flow__node')) return
              setSelectedNodeId(null)
              setSelectedNodeIds([])
            }}
          >
            <Canvas schemas={schemas} />
          </div>

          {/* Right sidebar */}
          <div className="w-64 bg-gray-900 border-l border-gray-700 flex flex-col overflow-y-auto">
            {selectedNode && !isGroupNodeData(selectedNode.data) && (
              <PropertiesPanel
                nodeId={selectedNode.id}
                schema={(selectedNode.data as CustomNodeData).schema}
                config={(selectedNode.data as CustomNodeData).config}
              />
            )}
            <div className="mt-auto border-t border-gray-700">
              {runError && (
                <div className="p-3 text-xs text-red-400 bg-red-950 border-b border-red-800">
                  <span className="font-semibold">Request failed: </span>{runError}
                </div>
              )}
              <ResultPanel result={executeResult} isRunning={isRunning} onReplay={handleReplay} />
            </div>
          </div>
        </div>

        {consoleLines.length > 0 && <ConsolePanel lines={consoleLines} />}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DctApp />
    </QueryClientProvider>
  )
}
