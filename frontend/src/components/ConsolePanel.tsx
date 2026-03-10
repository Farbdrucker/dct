import { useEffect, useMemo, useRef, useState } from 'react'
import AnsiToHtml from 'ansi-to-html'

const converter = new AnsiToHtml({ fg: '#d4d4d4', bg: '#1e1e1e', escapeXML: true })
const DEFAULT_HEIGHT = 200
const MIN_HEIGHT = 80

export function ConsolePanel({ lines }: { lines: string[] }) {
  const [height, setHeight] = useState(DEFAULT_HEIGHT)
  const [collapsed, setCollapsed] = useState(false)
  const htmlLines = useMemo(() => lines.map((l) => converter.toHtml(l)), [lines])
  const containerRef = useRef<HTMLPreElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    userScrolledUp.current = el.scrollHeight - el.scrollTop - el.clientHeight > 8
  }

  useEffect(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    }
  }, [lines])

  function onResizeMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    const startY = e.clientY
    const startH = height
    function onMouseMove(ev: MouseEvent) {
      setHeight(Math.max(MIN_HEIGHT, startH + (startY - ev.clientY)))
    }
    function onMouseUp() {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  return (
    <div
      className="border-t border-gray-700 bg-gray-900 flex flex-col flex-shrink-0"
      style={{ height: collapsed ? undefined : height }}
    >
      {/* Resize handle */}
      <div
        className="h-1 bg-gray-700 hover:bg-blue-500 cursor-ns-resize transition-colors flex-shrink-0"
        onMouseDown={onResizeMouseDown}
      />
      {/* Header */}
      <div className="flex items-center px-3 py-1.5 flex-shrink-0 select-none">
        <span className="text-xs font-semibold text-gray-400">
          Console ({lines.length} line{lines.length !== 1 ? 's' : ''})
        </span>
        <button
          onClick={() => setCollapsed(v => !v)}
          className="ml-auto text-gray-400 hover:text-gray-200 text-xs px-1 transition-colors"
        >
          {collapsed ? '▸' : '▾'}
        </button>
      </div>
      {/* Content */}
      {!collapsed && (
        <pre
          ref={containerRef}
          onScroll={handleScroll}
          className="flex-1 text-xs font-mono bg-gray-950 text-gray-200 px-3 py-2 overflow-auto leading-5 min-h-0"
        >
          {htmlLines.map((html, i) => (
            <div key={i} dangerouslySetInnerHTML={{ __html: html }} />
          ))}
          <div ref={bottomRef} />
        </pre>
      )}
    </div>
  )
}
