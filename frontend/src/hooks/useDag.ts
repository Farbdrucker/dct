import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import { create } from 'zustand'
import type { CustomNodeData } from '../components/CustomNode'
import { isGroupNodeData, type GroupNodeData } from '../components/GroupNode'

export type AnyNodeData = CustomNodeData | GroupNodeData

// ---------------------------------------------------------------------------
// Shared pure helper: apply collapse/expand transformation
// Used by store actions AND deserializer
// ---------------------------------------------------------------------------

interface RemappedEdgeData {
  originalEdge: {
    id: string
    source: string
    sourceHandle: string | null | undefined
    target: string
    targetHandle: string | null | undefined
  }
}

export function isRemappedEdge(e: Edge): boolean {
  return !!(e.data as RemappedEdgeData | undefined)?.originalEdge
}

export function applyCollapseTransform(
  groupId: string,
  nodes: Node<AnyNodeData>[],
  edges: Edge[],
): { nodes: Node<AnyNodeData>[]; edges: Edge[] } {
  const group = nodes.find((n) => n.id === groupId)
  if (!group || !isGroupNodeData(group.data)) return { nodes, edges }
  const gd = group.data
  const memberIds = new Set(gd.memberIds)

  const externalEdges = edges.filter(
    (e) => memberIds.has(e.source) !== memberIds.has(e.target),
  )
  const internalEdges = edges.filter(
    (e) => memberIds.has(e.source) && memberIds.has(e.target),
  )
  const unrelatedEdges = edges.filter(
    (e) => !memberIds.has(e.source) && !memberIds.has(e.target),
  )

  const remappedEdges: Edge[] = externalEdges.map((e) => {
    const srcIsMember = memberIds.has(e.source)
    return {
      id: `remapped-${e.id}`,
      source: srcIsMember ? groupId : e.source,
      sourceHandle: srcIsMember ? 'group-output' : e.sourceHandle,
      target: srcIsMember ? e.target : groupId,
      targetHandle: srcIsMember ? e.targetHandle : 'group-input',
      data: {
        originalEdge: {
          id: e.id,
          source: e.source,
          sourceHandle: e.sourceHandle,
          target: e.target,
          targetHandle: e.targetHandle,
        },
      } satisfies RemappedEdgeData,
    }
  })

  const newEdges: Edge[] = [
    ...unrelatedEdges,
    ...internalEdges.map((e) => ({ ...e, hidden: true })),
    ...remappedEdges,
  ]

  const newNodes = nodes.map((n) => {
    if (n.id === groupId) {
      return {
        ...n,
        zIndex: 0,
        style: { ...n.style, width: 200, height: 60 },
        data: { ...gd, collapsed: true } as GroupNodeData,
      }
    }
    if (memberIds.has(n.id)) return { ...n, hidden: true }
    return n
  })

  return { nodes: newNodes, edges: newEdges }
}

export function applyExpandTransform(
  groupId: string,
  nodes: Node<AnyNodeData>[],
  edges: Edge[],
): { nodes: Node<AnyNodeData>[]; edges: Edge[] } {
  const group = nodes.find((n) => n.id === groupId)
  if (!group || !isGroupNodeData(group.data)) return { nodes, edges }
  const gd = group.data
  const memberIds = new Set(gd.memberIds)

  const remapped = edges.filter(
    (e) =>
      isRemappedEdge(e) &&
      (e.source === groupId || e.target === groupId),
  )
  const restoredEdges: Edge[] = remapped.map((e) => {
    const orig = (e.data as unknown as RemappedEdgeData).originalEdge
    return {
      id: orig.id,
      source: orig.source,
      sourceHandle: orig.sourceHandle,
      target: orig.target,
      targetHandle: orig.targetHandle,
    }
  })

  const newEdges: Edge[] = [
    ...edges
      .filter((e) => !isRemappedEdge(e) || (e.source !== groupId && e.target !== groupId))
      .map((e) => (memberIds.has(e.source) && memberIds.has(e.target) ? { ...e, hidden: false } : e)),
    ...restoredEdges,
  ]

  const newNodes = nodes.map((n) => {
    if (n.id === groupId) {
      return {
        ...n,
        zIndex: -1,
        style: { ...n.style, width: gd.expandedWidth, height: gd.expandedHeight },
        data: { ...gd, collapsed: false } as GroupNodeData,
      }
    }
    if (memberIds.has(n.id)) return { ...n, hidden: false }
    return n
  })

  return { nodes: newNodes, edges: newEdges }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface DagState {
  nodes: Node<AnyNodeData>[]
  edges: Edge[]
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node<CustomNodeData>) => void
  removeNode: (id: string) => void
  updateNodeData: (id: string, data: Partial<CustomNodeData>) => void
  setNodes: (nodes: Node<AnyNodeData>[]) => void
  setEdges: (edges: Edge[]) => void
  groupNodes: (ids: string[], label: string) => void
  ungroupNodes: (groupId: string) => void
  toggleGroupCollapsed: (groupId: string) => void
}

const PADDING = 40

export const useDagStore = create<DagState>((set) => ({
  nodes: [],
  edges: [],

  onNodesChange: (changes) =>
    set((state) => {
      // Intercept 'remove' changes for group nodes — ungroup members before deleting
      const removedGroupIds = changes
        .filter((c) => c.type === 'remove')
        .map((c) => c.id)
        .filter((id) => isGroupNodeData(state.nodes.find((n) => n.id === id)?.data))

      let nodes = state.nodes as Node<AnyNodeData>[]
      let edges = state.edges

      for (const gid of removedGroupIds) {
        const group = nodes.find((n) => n.id === gid)
        if (!group || !isGroupNodeData(group.data)) continue
        const gd = group.data

        // If collapsed, expand first to restore edges
        if (gd.collapsed) {
          const result = applyExpandTransform(gid, nodes, edges)
          nodes = result.nodes
          edges = result.edges
        }

        // Restore absolute positions and remove parentId from members
        nodes = nodes.map((n) => {
          if (!gd.memberIds.includes(n.id)) return n
          return {
            ...n,
            parentId: undefined,
            extent: undefined,
            position: {
              x: n.position.x + group.position.x,
              y: n.position.y + group.position.y,
            },
          }
        })
      }

      nodes = applyNodeChanges(changes, nodes) as Node<AnyNodeData>[]
      return { nodes, edges }
    }),

  onEdgesChange: (changes) =>
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges) })),

  onConnect: (connection) =>
    set((state) => ({ edges: addEdge(connection, state.edges) })),

  addNode: (node) => set((state) => ({ nodes: [...state.nodes, node] })),

  removeNode: (id) =>
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
      edges: state.edges.filter((e) => e.source !== id && e.target !== id),
    })),

  updateNodeData: (id, data) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n,
      ),
    })),

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  groupNodes: (ids, label) =>
    set((state) => {
      if (ids.length < 2) return state

      // Only group visible nodes (not members of a collapsed group)
      const validIds = ids.filter((id) => {
        const n = state.nodes.find((x) => x.id === id)
        return n && !n.hidden
      })
      if (validIds.length < 2) return state

      const nodeById = new Map(state.nodes.map((n) => [n.id, n]))

      // Compute absolute positions
      const getAbsolutePos = (n: Node<AnyNodeData>) => {
        if (!n.parentId) return n.position
        const parent = nodeById.get(n.parentId)
        if (!parent) return n.position
        return { x: n.position.x + parent.position.x, y: n.position.y + parent.position.y }
      }

      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      for (const id of validIds) {
        const n = nodeById.get(id)
        if (!n) continue
        const pos = getAbsolutePos(n)
        const w = (n.measured?.width ?? 180)
        const h = (n.measured?.height ?? 80)
        minX = Math.min(minX, pos.x)
        minY = Math.min(minY, pos.y)
        maxX = Math.max(maxX, pos.x + w)
        maxY = Math.max(maxY, pos.y + h)
      }

      const groupX = minX - PADDING
      const groupY = minY - PADDING
      const groupW = (maxX - minX) + PADDING * 2
      const groupH = (maxY - minY) + PADDING * 2
      const groupId = `group-${Date.now()}`

      const groupNode: Node<GroupNodeData> = {
        id: groupId,
        type: 'group',
        position: { x: groupX, y: groupY },
        style: { width: groupW, height: groupH },
        zIndex: -1,
        data: {
          isGroup: true,
          label,
          memberIds: validIds,
          collapsed: false,
          expandedWidth: groupW,
          expandedHeight: groupH,
        },
      }

      const newNodes: Node<AnyNodeData>[] = [
        groupNode,
        ...state.nodes.map((n) => {
          if (!validIds.includes(n.id)) return n
          const absPos = getAbsolutePos(n)
          return {
            ...n,
            parentId: groupId,
            extent: 'parent' as const,
            position: { x: absPos.x - groupX, y: absPos.y - groupY },
          }
        }),
      ]

      return { nodes: newNodes }
    }),

  ungroupNodes: (groupId) =>
    set((state) => {
      const group = state.nodes.find((n) => n.id === groupId)
      if (!group || !isGroupNodeData(group.data)) return state

      const gd = group.data
      let { nodes, edges } = state

      if (gd.collapsed) {
        const result = applyExpandTransform(groupId, nodes, edges)
        nodes = result.nodes
        edges = result.edges
      }

      // Must re-read group after potential expand (position unchanged, but data changes)
      const updatedGroup = nodes.find((n) => n.id === groupId)!

      const newNodes = nodes
        .filter((n) => n.id !== groupId)
        .map((n) => {
          if (!gd.memberIds.includes(n.id)) return n
          return {
            ...n,
            parentId: undefined,
            extent: undefined,
            position: {
              x: n.position.x + updatedGroup.position.x,
              y: n.position.y + updatedGroup.position.y,
            },
          }
        })

      const newEdges = edges.filter(
        (e) => e.source !== groupId && e.target !== groupId,
      )

      return { nodes: newNodes, edges: newEdges }
    }),

  toggleGroupCollapsed: (groupId) =>
    set((state) => {
      const group = state.nodes.find((n) => n.id === groupId)
      if (!group || !isGroupNodeData(group.data)) return state

      const gd = group.data
      if (gd.collapsed) {
        return applyExpandTransform(groupId, state.nodes, state.edges)
      } else {
        return applyCollapseTransform(groupId, state.nodes, state.edges)
      }
    }),
}))
