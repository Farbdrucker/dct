import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { fetchSchema } from '../api/client'
import type { SchemaResponse } from '../api/types'

export function useSchema() {
  const prevVersion = useRef<string | null>(null)

  const query = useQuery<SchemaResponse>({
    queryKey: ['schema'],
    queryFn: fetchSchema,
    refetchInterval: 2000,
    staleTime: 0,
  })

  useEffect(() => {
    if (!query.data) return
    const version = query.data.schema_version
    if (prevVersion.current !== null && prevVersion.current !== version) {
      console.info('[DCT] Schema updated:', version)
    }
    prevVersion.current = version
  }, [query.data?.schema_version])

  return query
}
