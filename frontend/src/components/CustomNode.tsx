import { Handle, Position, useEdges, type NodeProps } from '@xyflow/react'
import Markdown from 'react-markdown'
import type { NodeSchema } from '../api/types'
import { useDagStore } from '../hooks/useDag'

export interface CustomNodeData extends Record<string, unknown> {
  schemaName: string
  schema: NodeSchema
  config: Record<string, unknown>
  constants: Record<string, unknown>
}

const TYPE_COLORS: Record<string, string> = {
  int: 'bg-blue-500',
  float: 'bg-green-500',
  str: 'bg-yellow-500',
  bool: 'bg-purple-500',
}

function typeColor(typeSet: string[]): string {
  const first = typeSet[0]
  return TYPE_COLORS[first] ?? 'bg-gray-500'
}

function TypeBadge({ typeSet }: { typeSet: string[] }) {
  const color = typeColor(typeSet)
  return (
    <span className={`text-white text-xs px-1 rounded ${color}`}>
      {typeSet.join(' | ')}
    </span>
  )
}

export function CustomNode({ id, data, selected }: NodeProps) {
  const { schema, config, constants } = data as CustomNodeData
  const edges = useEdges()
  const updateNodeData = useDagStore((s) => s.updateNodeData)
  const removeNode = useDagStore((s) => s.removeNode)

  const connectedInputs = new Set(
    edges.filter((e) => e.target === id).map((e) => e.targetHandle)
  )

  return (
    <div
      className={`bg-white border-2 rounded-lg shadow-md min-w-[180px] ${
        selected ? 'border-blue-500' : 'border-gray-300'
      }`}
    >
      {/* Header */}
      <div className="bg-gray-800 text-white text-sm font-semibold px-3 py-1.5 rounded-t-lg flex items-center justify-between">
        <span>{schema.class_name}</span>
        <button
          onClick={(e) => { e.stopPropagation(); removeNode(id) }}
          className="ml-2 text-gray-400 hover:text-white leading-none"
          title="Remove node"
        >
          ×
        </button>
      </div>

      <div className="px-3 py-2 space-y-1 text-xs text-gray-700">
        {/* Docstring */}
        {schema.description && (
          <div className="prose prose-xs max-w-none text-gray-500 border-b border-gray-200 pb-1 mb-1">
            <Markdown>{schema.description}</Markdown>
          </div>
        )}
        {/* Input ports */}
        {schema.input_ports.map((port) => (
          <div key={port.name} className="flex items-center gap-2 relative">
            <Handle
              type="target"
              position={Position.Left}
              id={port.name}
              style={{ left: -10 }}
              data-typeset={JSON.stringify(port.type_set)}
            />
            <span className="font-mono">{port.name}</span>
            <TypeBadge typeSet={port.type_set} />
            {/* Inline constant input when port has no incoming edge */}
            {!connectedInputs.has(port.name) && (
              <input
                className="ml-auto border border-gray-300 rounded px-1 w-16 text-xs"
                placeholder="value"
                value={String(constants[port.name] ?? '')}
                onChange={(e) => {
                  const raw = e.target.value
                  const num = Number(raw)
                  const val = raw === '' ? '' : isNaN(num) ? raw : num
                  updateNodeData(id, {
                    constants: { ...constants, [port.name]: val },
                  })
                }}
              />
            )}
          </div>
        ))}

        {/* Config fields */}
        {schema.config_fields.map((field) => (
          <div key={field.name} className="flex items-center gap-2">
            <span className="font-mono text-gray-500">{field.name}:</span>
            <TypeBadge typeSet={field.type_set} />
            <input
              className="ml-auto border border-gray-300 rounded px-1 w-16 text-xs"
              placeholder={field.required ? 'required' : 'optional'}
              value={String(config[field.name] ?? '')}
              onChange={(e) => {
                const raw = e.target.value
                const num = Number(raw)
                const val = raw === '' ? '' : isNaN(num) ? raw : num
                updateNodeData(id, {
                  config: { ...config, [field.name]: val },
                })
              }}
            />
          </div>
        ))}

        {/* Output port — omitted for sinks */}
        {schema.output_port && (
          <div className="flex items-center gap-2 justify-end relative">
            <span className="font-mono">output</span>
            <TypeBadge typeSet={schema.output_port.type_set} />
            <Handle
              type="source"
              position={Position.Right}
              id="output"
              style={{ right: -10 }}
              data-typeset={JSON.stringify(schema.output_port.type_set)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
