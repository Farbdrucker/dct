import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useDagStore } from '../hooks/useDag'

export interface GroupNodeData extends Record<string, unknown> {
  isGroup: true
  label: string
  memberIds: string[]
  collapsed: boolean
  expandedWidth: number
  expandedHeight: number
}

export function isGroupNodeData(data: unknown): data is GroupNodeData {
  return typeof data === 'object' && data !== null && (data as GroupNodeData).isGroup === true
}

export function GroupNode({ id, data, selected }: NodeProps) {
  const gd = data as GroupNodeData
  const toggleGroupCollapsed = useDagStore((s) => s.toggleGroupCollapsed)
  const ungroupNodes = useDagStore((s) => s.ungroupNodes)

  if (gd.collapsed) {
    return (
      <div
        className={`bg-gray-800 border-2 rounded-lg shadow-lg w-full h-full flex items-center justify-between px-3 ${
          selected ? 'border-blue-400' : 'border-indigo-500'
        }`}
      >
        <Handle type="target" position={Position.Left} id="group-input" />

        <div className="flex flex-col min-w-0">
          <span className="text-white text-sm font-semibold truncate">{gd.label}</span>
          <span className="text-gray-400 text-xs">{gd.memberIds.length} nodes</span>
        </div>

        <div className="flex gap-1 ml-2 shrink-0">
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              toggleGroupCollapsed(id)
            }}
            className="text-gray-400 hover:text-white text-xs px-1 py-0.5 rounded hover:bg-gray-700"
            title="Expand group"
          >
            ⊞
          </button>
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              ungroupNodes(id)
            }}
            className="text-gray-400 hover:text-red-400 text-xs px-1 py-0.5 rounded hover:bg-gray-700"
            title="Ungroup"
          >
            ×
          </button>
        </div>

        <Handle type="source" position={Position.Right} id="group-output" />
      </div>
    )
  }

  // Expanded — render as a labeled frame
  return (
    <div
      className={`rounded-xl border-2 w-full h-full bg-indigo-950/30 ${
        selected ? 'border-blue-400' : 'border-indigo-600/60'
      }`}
      style={{ pointerEvents: 'none' }}
    >
      <div
        className="flex items-center justify-between px-3 py-1.5 rounded-t-xl"
        style={{ pointerEvents: 'all' }}
      >
        <span className="text-indigo-300 text-xs font-semibold select-none">{gd.label}</span>
        <div className="flex gap-1">
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              toggleGroupCollapsed(id)
            }}
            className="text-indigo-400 hover:text-white text-xs px-1 py-0.5 rounded hover:bg-indigo-800"
            title="Collapse group"
          >
            ⊟
          </button>
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              ungroupNodes(id)
            }}
            className="text-indigo-400 hover:text-red-400 text-xs px-1 py-0.5 rounded hover:bg-indigo-800"
            title="Ungroup"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  )
}
