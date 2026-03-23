import type { Edge, Node } from '@xyflow/react'
import type { DagPayload, NodeSchema } from '../api/types'
import type { CustomNodeData } from '../components/CustomNode'
import { isGroupNodeData, type GroupNodeData } from '../components/GroupNode'
import { applyCollapseTransform, isRemappedEdge, type AnyNodeData } from '../hooks/useDag'

// ---------------------------------------------------------------------------
// Saved DAG formats
// ---------------------------------------------------------------------------

interface SavedRegularNode {
  id: string
  schemaName: string
  position: { x: number; y: number }
  config: Record<string, unknown>
  constants: Record<string, unknown>
  parentId?: string
}

interface SavedGroupNode {
  id: string
  schemaName: '__group__'
  position: { x: number; y: number }
  config: Record<string, unknown>
  constants: Record<string, unknown>
  label: string
  memberIds: string[]
  collapsed: boolean
  width: number
  height: number
  parentId?: string
}

type SavedNode = SavedRegularNode | SavedGroupNode

interface SavedEdge {
  id: string
  source: string
  sourceHandle: string
  target: string
  targetHandle: string
}

interface SavedDagV1 {
  version: 1
  nodes: SavedRegularNode[]
  edges: SavedEdge[]
}

interface SavedDagV2 {
  version: 2
  nodes: SavedNode[]
  edges: SavedEdge[]
}

type SavedDag = SavedDagV1 | SavedDagV2

// ---------------------------------------------------------------------------
// Export (SavedDag v2)
// ---------------------------------------------------------------------------

export function exportDagToJson(nodes: Node<AnyNodeData>[], edges: Edge[]): string {
  // Determine "original" edges: exclude remapped synthetic edges, but
  // restore their originals. Hidden internal edges are original — keep them.
  const restoredFromRemapped: SavedEdge[] = edges
    .filter(isRemappedEdge)
    .map((e) => {
      const orig = (e.data as { originalEdge: SavedEdge }).originalEdge
      return { id: orig.id, source: orig.source, sourceHandle: orig.sourceHandle ?? 'output', target: orig.target, targetHandle: orig.targetHandle ?? '' }
    })

  const regularEdges: SavedEdge[] = edges
    .filter((e) => !isRemappedEdge(e))
    .map((e) => ({
      id: e.id,
      source: e.source,
      sourceHandle: e.sourceHandle ?? 'output',
      target: e.target,
      targetHandle: e.targetHandle ?? '',
    }))

  const saved: SavedDagV2 = {
    version: 2,
    nodes: nodes.map((n): SavedNode => {
      if (isGroupNodeData(n.data)) {
        const gd = n.data
        return {
          id: n.id,
          schemaName: '__group__',
          position: n.position,
          config: {},
          constants: {},
          label: gd.label,
          memberIds: gd.memberIds,
          collapsed: gd.collapsed,
          width: gd.expandedWidth,
          height: gd.expandedHeight,
          ...(n.parentId ? { parentId: n.parentId } : {}),
        }
      }
      const cd = n.data as CustomNodeData
      return {
        id: n.id,
        schemaName: cd.schemaName,
        position: n.position,
        config: cd.config,
        constants: cd.constants,
        ...(n.parentId ? { parentId: n.parentId } : {}),
      }
    }),
    edges: [...regularEdges, ...restoredFromRemapped],
  }

  return JSON.stringify(saved, null, 2)
}

function _autoPosition(index: number): { x: number; y: number } {
  const cols = 4
  return { x: 80 + (index % cols) * 260, y: 80 + Math.floor(index / cols) * 160 }
}

// ---------------------------------------------------------------------------
// Import (v1 and v2)
// ---------------------------------------------------------------------------

export function parseDagFromJson(
  json: string,
  schemasByName: Record<string, NodeSchema>,
): { nodes: Node<AnyNodeData>[]; edges: Edge[] } {
  const parsed: unknown = JSON.parse(json)

  // DagPayload format (no 'version' key) — flat nodes, no groups
  if (parsed !== null && typeof parsed === 'object' && !('version' in parsed)) {
    const payload = parsed as DagPayload
    const nodes: Node<CustomNodeData>[] = payload.nodes.map((n, i) => {
      const schema = schemasByName[n.type]
      if (!schema) throw new Error(`Unknown node type "${n.type}" in payload`)
      return {
        id: n.id,
        type: 'custom',
        position: _autoPosition(i),
        data: { schemaName: n.type, schema, config: n.data.config, constants: n.data.constants },
      }
    })
    const edges: Edge[] = payload.edges.map((e) => ({
      id: e.id,
      source: e.source,
      sourceHandle: e.source_handle,
      target: e.target,
      targetHandle: e.target_handle,
    }))
    return { nodes, edges }
  }

  const saved = parsed as SavedDag

  // v1 — original behavior (no groups)
  if (saved.version === 1) {
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

  // v2 — groups supported
  const groupNodes: Node<GroupNodeData>[] = []
  const regularNodes: Node<CustomNodeData>[] = []

  for (const n of (saved as SavedDagV2).nodes) {
    if (n.schemaName === '__group__') {
      const gn = n as SavedGroupNode
      groupNodes.push({
        id: gn.id,
        type: 'group',
        position: gn.position,
        // expanded dimensions — collapse transform will adjust if needed
        style: { width: gn.width, height: gn.height },
        zIndex: -1,
        ...(gn.parentId ? { parentId: gn.parentId } : {}),
        data: {
          isGroup: true,
          label: gn.label,
          memberIds: gn.memberIds,
          collapsed: false, // start expanded; apply collapse below if needed
          expandedWidth: gn.width,
          expandedHeight: gn.height,
        },
      })
    } else {
      const rn = n as SavedRegularNode
      const schema = schemasByName[rn.schemaName]
      if (!schema) throw new Error(`Unknown node type "${rn.schemaName}" in saved DAG`)
      regularNodes.push({
        id: rn.id,
        type: 'custom',
        position: rn.position,
        ...(rn.parentId ? { parentId: rn.parentId } : {}),
        data: { schemaName: rn.schemaName, schema, config: rn.config, constants: rn.constants },
      })
    }
  }

  // Parents must appear before children in xyflow
  let allNodes: Node<AnyNodeData>[] = [...groupNodes, ...regularNodes]

  let allEdges: Edge[] = (saved as SavedDagV2).edges.map((e) => ({
    id: e.id,
    source: e.source,
    sourceHandle: e.sourceHandle,
    target: e.target,
    targetHandle: e.targetHandle,
  }))

  // Apply collapse for groups that were saved in collapsed state
  for (const gn of (saved as SavedDagV2).nodes.filter(
    (n): n is SavedGroupNode => n.schemaName === '__group__' && (n as SavedGroupNode).collapsed,
  )) {
    const result = applyCollapseTransform(gn.id, allNodes, allEdges)
    allNodes = result.nodes
    allEdges = result.edges
  }

  return { nodes: allNodes, edges: allEdges }
}

// ---------------------------------------------------------------------------
// URL hash encoding / decoding
// ---------------------------------------------------------------------------

/** Encode current DAG to a base64 string (compact JSON, unicode-safe). */
export function encodeDagToHash(nodes: Node<AnyNodeData>[], edges: Edge[]): string {
  const json = exportDagToJson(nodes, edges)
  // Compact (remove pretty-print whitespace) to reduce URL length
  return btoa(unescape(encodeURIComponent(JSON.stringify(JSON.parse(json)))))
}

/** Decode a base64 hash string back to JSON. Returns null on any failure. */
export function decodeDagFromHash(hash: string): string | null {
  try {
    return decodeURIComponent(escape(atob(hash)))
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// API payload serialization (groups stripped, original edges restored)
// ---------------------------------------------------------------------------

export function serializeDag(nodes: Node<AnyNodeData>[], edges: Edge[]): DagPayload {
  // Only regular (non-group) nodes
  const regularNodes = nodes.filter((n) => !isGroupNodeData(n.data)) as Node<CustomNodeData>[]

  // Restore original edges from remapped ones; keep all other edges (including hidden internals)
  const restoredFromRemapped = edges
    .filter(isRemappedEdge)
    .map((e) => {
      const orig = (e.data as { originalEdge: { id: string; source: string; sourceHandle: string | null | undefined; target: string; targetHandle: string | null | undefined } }).originalEdge
      return {
        id: orig.id,
        source: orig.source,
        source_handle: orig.sourceHandle ?? 'output',
        target: orig.target,
        target_handle: orig.targetHandle ?? '',
      }
    })

  const regularEdges = edges
    .filter((e) => !isRemappedEdge(e))
    .map((e) => ({
      id: e.id,
      source: e.source,
      source_handle: e.sourceHandle ?? 'output',
      target: e.target,
      target_handle: e.targetHandle ?? '',
    }))

  return {
    nodes: regularNodes.map((n) => ({
      id: n.id,
      type: n.data.schemaName,
      data: {
        config: n.data.config,
        constants: n.data.constants,
      },
    })),
    edges: [...regularEdges, ...restoredFromRemapped],
  }
}
