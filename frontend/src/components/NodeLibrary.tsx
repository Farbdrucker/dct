import type { NodeSchema } from '../api/types'

interface Props {
  schemas: NodeSchema[]
  onAdd: (schema: NodeSchema) => void
}

function Section({ title, schemas, onAdd }: { title: string; schemas: NodeSchema[]; onAdd: (s: NodeSchema) => void }) {
  if (schemas.length === 0) return null
  return (
    <div>
      <div className="px-3 pt-3 pb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        {title}
      </div>
      <div className="space-y-0.5">
        {schemas.map((s) => (
          <button
            key={s.class_name}
            onClick={() => onAdd(s)}
            className="w-full text-left text-sm px-3 py-2 rounded hover:bg-gray-700 transition-colors"
          >
            <div className="font-medium">{s.class_name}</div>
            <div className="text-gray-400 text-xs mt-0.5">
              {s.kind === 'source'
                ? `→ ${s.output_port.type}`
                : `(${s.input_ports.map((p) => p.name).join(', ')}) → ${s.output_port.type}`}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

export function NodeLibrary({ schemas, onAdd }: Props) {
  const transitions = schemas.filter((s) => s.kind === 'transition')
  const sources = schemas.filter((s) => s.kind === 'source')

  return (
    <div className="w-52 bg-gray-900 text-white flex flex-col">
      <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-400 border-b border-gray-700">
        Node Library
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        <Section title="Sources" schemas={sources} onAdd={onAdd} />
        <Section title="Transitions" schemas={transitions} onAdd={onAdd} />
      </div>
    </div>
  )
}
