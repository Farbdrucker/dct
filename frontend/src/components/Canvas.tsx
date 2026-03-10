import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge,
  type IsValidConnection,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback } from 'react'
import type { NodeSchema } from '../api/types'
import { useDagStore } from '../hooks/useDag'
import { isCompatible } from '../utils/typeCompat'
import { CustomNode, type CustomNodeData } from './CustomNode'

const nodeTypes: NodeTypes = { custom: CustomNode }

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
  const data = node.data as CustomNodeData
  const schema = data.schema
  if (handleId === 'output') {
    return schema.output_port.type_set
  }
  const port = schema.input_ports.find((p) => p.name === handleId)
  return port?.type_set ?? []
}

export function Canvas({ schemas: _schemas }: Props) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect } = useDagStore()

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

      const src = getHandleTypeSet(conn.source, 'output', nodes)
      const tgt = getHandleTypeSet(conn.target, conn.targetHandle, nodes)
      return isCompatible(src, tgt)
    },
    [nodes, edges],
  )

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      isValidConnection={isValidConnection}
      nodeTypes={nodeTypes}
      fitView
      deleteKeyCode="Delete"
    >
      <Background />
      <Controls />
      <MiniMap />
    </ReactFlow>
  )
}
