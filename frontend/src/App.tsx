import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import type { Node } from '@xyflow/react'
import { executeDag, executeStream } from './api/client'
import type { NodeSchema } from './api/types'
import { Canvas } from './components/Canvas'
import { ConsolePanel } from './components/ConsolePanel'
import { NodeLibrary } from './components/NodeLibrary'
import { PropertiesPanel } from './components/PropertiesPanel'
import { ResultPanel } from './components/ResultPanel'
import type { CustomNodeData } from './components/CustomNode'
import { useDagStore } from './hooks/useDag'
import { useSchema } from './hooks/useSchema'
import { useUiStore } from './store/uiStore'
import { exportDagToJson, parseDagFromJson, serializeDag } from './utils/dagSerializer'

const queryClient = new QueryClient()

function DctApp() {
  const { data: schemaData, isLoading, isError, error } = useSchema()
  const schemas = schemaData?.nodes ?? []
  const { nodes, edges, addNode, setNodes, setEdges } = useDagStore()
  const { selectedNodeId, setSelectedNodeId, executeResult, setExecuteResult, isRunning, setIsRunning, captureConsole, setCaptureConsole, parallel, setParallel } =
    useUiStore()

  const [consoleLines, setConsoleLines] = useState<string[]>([])

  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

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
    try {
      const payload = { ...serializeDag(nodes, edges), capture_logs: captureConsole, parallel }
      if (captureConsole) {
        await executeStream(
          payload,
          (line) => setConsoleLines((prev) => [...prev, line]),
          (result) => setExecuteResult(result),
        )
      } else {
        const result = await executeDag(payload)
        setExecuteResult(result)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setIsRunning(false)
    }
  }, [nodes, edges, setIsRunning, setExecuteResult, captureConsole, parallel])

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
          <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
            <input type="checkbox" checked={captureConsole} onChange={e => setCaptureConsole(e.target.checked)} className="accent-green-500" />
            Console
          </label>
          <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
            <input type="checkbox" checked={parallel} onChange={e => setParallel(e.target.checked)} className="accent-blue-500" />
            Parallel
          </label>
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
            }}
          >
            <Canvas schemas={schemas} />
          </div>

          {/* Right sidebar */}
          <div className="w-64 bg-gray-900 border-l border-gray-700 flex flex-col overflow-y-auto">
            {selectedNode && (
              <PropertiesPanel
                nodeId={selectedNode.id}
                schema={selectedNode.data.schema}
                config={selectedNode.data.config}
              />
            )}
            <div className="mt-auto border-t border-gray-700">
              <ResultPanel result={executeResult} isRunning={isRunning} />
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
