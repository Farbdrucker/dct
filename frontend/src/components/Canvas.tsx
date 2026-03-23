import {
  Background,
  getBezierPath,
  Position,
  ReactFlow,
  type Connection,
  type ConnectionLineComponentProps,
  type Edge,
  type IsValidConnection,
  type Node,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect } from 'react'
import type { NodeSchema } from '../api/types'
import { useDagStore } from '../hooks/useDag'
import { useUiStore } from '../store/uiStore'
import { isCompatible } from '../utils/typeCompat'
import { CustomNode, type CustomNodeData } from './CustomNode'
import { GroupNode, isGroupNodeData } from './GroupNode'

function LiveConnectionLine({ fromX, fromY, toX, toY, fromPosition, toPosition, connectionStatus }: ConnectionLineComponentProps) {
  const [path] = getBezierPath({
    sourceX: fromX,
    sourceY: fromY,
    sourcePosition: fromPosition ?? Position.Right,
    targetX: toX,
    targetY: toY,
    targetPosition: toPosition ?? Position.Left,
  })
  const stroke =
    connectionStatus === 'valid'   ? '#22c55e' :
    connectionStatus === 'invalid' ? '#ef4444' : '#94a3b8'
  return (
    <g>
      {/* Use style={{}} not SVG presentation attrs — inline style wins over any CSS class */}
      <path
        style={{ fill: 'none', stroke, strokeWidth: 3, strokeDasharray: '6 3', strokeLinecap: 'round' }}
        d={path}
      />
      <circle
        style={{ fill: stroke, stroke: 'white', strokeWidth: 1.5 }}
        cx={toX}
        cy={toY}
        r={4}
      />
    </g>
  )
}

const nodeTypes: NodeTypes = { custom: CustomNode, group: GroupNode }

interface Props {
  schemas: NodeSchema[]
}

function getHandleTypeSet(
  nodeId: string,
  handleId: string | null | undefined,
  nodes: { id: string; data: Record<string, unknown> }[],
): string[] {
  const node = nodes.find((n) => n.id === nodeId)
  if (!node) return []
  if (isGroupNodeData(node.data)) return []
  const data = node.data as CustomNodeData
  const schema = data.schema
  if (handleId === 'output') {
    return schema.output_port?.type_set ?? []
  }
  const port = schema.input_ports.find((p) => p.name === handleId)
  return port?.type_set ?? []
}

export function Canvas({ schemas: _schemas }: Props) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setNodes, setEdges } = useDagStore()
  const { setSelectedNodeIds, selectedNodeIds, clipboard, setClipboard } = useUiStore()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.metaKey && !e.ctrlKey) return
      const tag = (e.target as HTMLElement).tagName.toLowerCase()
      if (tag === 'input' || tag === 'textarea') return

      if (e.key === 'c') {
        // Build the full set of nodes to copy: selected nodes + members of selected groups
        const nodeById = new Map(nodes.map((n) => [n.id, n]))
        const toCopy = new Map<string, Node>()

        const collect = (n: Node) => {
          if (toCopy.has(n.id)) return
          toCopy.set(n.id, n)
          if (isGroupNodeData(n.data)) {
            ;(n.data as { memberIds: string[] }).memberIds.forEach((mid) => {
              const member = nodeById.get(mid)
              if (member) collect(member)
            })
          }
        }

        nodes
          .filter((n) => selectedNodeIds.includes(n.id) && !n.hidden)
          .forEach(collect)

        if (toCopy.size === 0) return
        const copiedIds = new Set(toCopy.keys())
        const copiedEdges = edges.filter(
          (edge) => copiedIds.has(edge.source) && copiedIds.has(edge.target),
        )
        setClipboard({ nodes: Array.from(toCopy.values()) as Node[], edges: copiedEdges })
        e.preventDefault()

      } else if (e.key === 'v' && clipboard) {
        const ts = Date.now()
        const idMap = new Map<string, string>()
        clipboard.nodes.forEach((n, i) => idMap.set(n.id, `${n.type}-${ts}-${i}`))

        const newNodes: Node[] = clipboard.nodes.map((n) => {
          const newId = idMap.get(n.id)!

          if (isGroupNodeData(n.data)) {
            const gd = n.data as { memberIds: string[]; [k: string]: unknown }
            return {
              id: newId,
              type: n.type,
              position: { x: n.position.x + 30, y: n.position.y + 30 },
              style: n.style,
              zIndex: n.zIndex ?? -1,
              selected: false,
              data: { ...gd, memberIds: gd.memberIds.map((mid) => idMap.get(mid) ?? mid) },
            }
          }

          if (n.parentId && idMap.has(n.parentId)) {
            // member node: remap parentId, keep relative position (group is the offset anchor)
            return {
              id: newId,
              type: n.type,
              position: n.position,
              data: n.data,
              parentId: idMap.get(n.parentId)!,
              extent: 'parent' as const,
              hidden: n.hidden,
              selected: false,
            }
          }

          // plain node
          return {
            id: newId,
            type: n.type,
            position: { x: n.position.x + 30, y: n.position.y + 30 },
            data: n.data,
            selected: false,
          }
        })

        const newEdges: Edge[] = clipboard.edges.map((edge, i) => ({
          id: `edge-${ts}-${i}`,
          source: idMap.get(edge.source) ?? edge.source,
          sourceHandle: edge.sourceHandle,
          target: idMap.get(edge.target) ?? edge.target,
          targetHandle: edge.targetHandle,
        }))

        setNodes([...nodes, ...newNodes] as Parameters<typeof setNodes>[0])
        setEdges([...edges, ...newEdges])
        e.preventDefault()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [nodes, edges, selectedNodeIds, clipboard, setClipboard, setNodes, setEdges])

  const isValidConnection = useCallback<IsValidConnection<Edge>>(
    (connection) => {
      const conn = connection as Connection
      // Reject duplicate edges to same target+handle
      const existing = edges.find(
        (e) =>
          e.target === conn.target &&
          e.targetHandle === conn.targetHandle,
      )
      if (existing) return false

      // Allow any connection involving a group node (no type checking on group handles)
      if (
        isGroupNodeData(nodes.find((n) => n.id === conn.source)?.data) ||
        isGroupNodeData(nodes.find((n) => n.id === conn.target)?.data)
      ) return true

      const src = getHandleTypeSet(conn.source, 'output', nodes)
      const tgt = getHandleTypeSet(conn.target, conn.targetHandle, nodes)
      return isCompatible(src, tgt)
    },
    [nodes, edges],
  )

  const handleSelectionChange = useCallback(
    ({ nodes: sel }: { nodes: Node[] }) => {
      setSelectedNodeIds(sel.map((n) => n.id))
    },
    [setSelectedNodeIds],
  )

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      isValidConnection={isValidConnection}
      onSelectionChange={handleSelectionChange}
      nodeTypes={nodeTypes}
      connectionLineComponent={LiveConnectionLine}
      fitView
      deleteKeyCode="Delete"
    >
      <Background />
    </ReactFlow>
  )
}
