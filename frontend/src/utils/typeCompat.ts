/**
 * Mirror of Python is_compatible():
 * source must be a subset of target, empty = any.
 */
export function isCompatible(source: string[], target: string[]): boolean {
  if (source.length === 0 || target.length === 0) return true
  const targetSet = new Set(target)
  return source.every((t) => targetSet.has(t))
}
