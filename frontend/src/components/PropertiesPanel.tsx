import Form from '@rjsf/core'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'
import type { NodeSchema } from '../api/types'
import { useDagStore } from '../hooks/useDag'

interface Props {
  nodeId: string
  schema: NodeSchema
  config: Record<string, unknown>
}

export function PropertiesPanel({ nodeId, schema, config }: Props) {
  const updateNodeData = useDagStore((s) => s.updateNodeData)

  if (schema.config_fields.length === 0) {
    return (
      <div className="p-3 text-xs text-gray-400">No config fields.</div>
    )
  }

  const jsonSchema: RJSFSchema = {
    type: 'object',
    required: schema.config_fields.filter((f) => f.required).map((f) => f.name),
    properties: Object.fromEntries(
      schema.config_fields.map((f) => [f.name, f.json_schema as RJSFSchema])
    ),
  }

  return (
    <div className="p-3">
      <div className="text-xs font-semibold text-gray-500 mb-2">Config — {schema.class_name}</div>
      <Form
        schema={jsonSchema}
        validator={validator}
        formData={config}
        onChange={({ formData }) => updateNodeData(nodeId, { config: formData ?? {} })}
        uiSchema={{ 'ui:submitButtonOptions': { norender: true } }}
      />
    </div>
  )
}
