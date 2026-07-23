import { useRef, useState, useCallback, useEffect } from 'react'
import type { SSEDoneEvent, RunStatus, TraceRecord } from '../types'

interface UseSSEOptions {
  onPhase: (phase: string, summary: string) => void
  onDone: (data: SSEDoneEvent) => void
  onTrace?: (record: TraceRecord) => void
  onTitle?: (title: string, conversationId: string) => void
}

interface UseSSEReturn {
  status: RunStatus
  start: (
    question: string,
    context: string,
    mode: string,
    conversationId: string,
    files?: string[],
    projectId?: string,
  ) => void
  stop: () => void
}

export function useSSE({ onPhase, onDone, onTrace, onTitle }: UseSSEOptions): UseSSEReturn {
  const [status, setStatus] = useState<RunStatus>('idle')
  const esRef = useRef<EventSource | null>(null)

  const stop = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
    setStatus('idle')
  }, [])

  const start = useCallback((
    question: string,
    context: string,
    mode: string,
    conversationId: string,
    files: string[] = [],
    projectId: string = '',
  ) => {
    stop()

    let url = '/api/v1/agent/run/stream'
      + '?question=' + encodeURIComponent(question)
      + '&context=' + encodeURIComponent(context)
      + '&mode=' + encodeURIComponent(mode)
    // 关键：携带 conversation_id，否则 episode 以空 id 保存、历史列表永远为空
    if (conversationId) url += '&conversation_id=' + encodeURIComponent(conversationId)
    if (files.length > 0) url += '&files=' + encodeURIComponent(files.join(','))
    // project_id 始终携带（空串=默认项目），确保后端正确归属
    url += '&project_id=' + encodeURIComponent(projectId)

    const es = new EventSource(url + '&dev_trace=1')
    esRef.current = es
    setStatus('running')

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.heartbeat) return
        if (data.type === 'title') {
          if (onTitle) onTitle(data.title, data.conversation_id || '')
          return
        }
        if (data.done) {
          setStatus('done')
          es.close()
          esRef.current = null
          onDone(data as SSEDoneEvent)
        } else if (data.phase) {
          onPhase(data.phase, data.summary || '')
          if (onTrace && data.trace) {
            onTrace(data.trace as TraceRecord)
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      setStatus('error')
      es.close()
      esRef.current = null
    }
  }, [stop, onPhase, onDone, onTrace, onTitle])

  useEffect(() => {
    return () => { if (esRef.current) esRef.current.close() }
  }, [])

  return { status, start, stop }
}
