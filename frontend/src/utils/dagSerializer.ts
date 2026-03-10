import type { Edge, Node } from '@xyflow/react'
import type { DagPayload, NodeSchema } from '../api/types'
import type { CustomNodeData } from '../components/CustomNode'

// ---------------------------------------------------------------------------
// Saved DAG format (for export/import)
// ---------------------------------------------------------------------------

interface SavedNode {
  id: string
  schemaName: string
  position: { x: number; y: number }
  config: Record<string, unknown>
  constants: Record<string, unknown>
}

interface SavedEdge {
  id: string
  source: string
  sourceHandle: string
  target: string
  targetHandle: string
}

interface SavedDag {
  version: 1
  nodes: SavedNode[]
  edges: SavedEdge[]
}

export function exportDagToJson(nodes: Node<CustomNodeData>[], edges: Edge[]): string {
  const saved: SavedDag = {
    version: 1,
    nodes: nodes.map((n) => ({
      id: n.id,
      schemaName: n.data.schemaName,
      position: n.position,
      config: n.data.config,
      constants: n.data.constants,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      sourceHandle: e.sourceHandle ?? 'output',
      target: e.target,
      targetHandle: e.targetHandle ?? '',
    })),
  }
  return JSON.stringify(saved, null, 2)
}

export function parseDagFromJson(
  json: string,
  schemasByName: Record<string, NodeSchema>,
): { nodes: Node<CustomNodeData>[]; edges: Edge[] } {
  const saved: SavedDag = JSON.parse(json)

  const nodes: Node<CustomNodeData>[] = saved.nodes.map((n) => {
    const schema = schemasByName[n.schemaName]
    if (!schema) throw new Error(`Unknown node type "${n.schemaName}" in saved DAG`)
    return {
      id: n.id,
      type: 'custom',
      position: n.position,
      data: { schemaName: n.schemaName, schema, config: n.config, constants: n.constants },
    }
  })

  const edges: Edge[] = saved.edges.map((e) => ({
    id: e.id,
    source: e.source,
    sourceHandle: e.sourceHandle,
    target: e.target,
    targetHandle: e.targetHandle,
  }))

  return { nodes, edges }
}

// ---------------------------------------------------------------------------
// API payload serialization
// ---------------------------------------------------------------------------

export function serializeDag(nodes: Node<CustomNodeData>[], edges: Edge[]): DagPayload {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.schemaName,
      data: {
        config: n.data.config,
        constants: n.data.constants,
      },
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      source_handle: e.sourceHandle ?? 'output',
      target: e.target,
      target_handle: e.targetHandle ?? '',
    })),
  }
}
