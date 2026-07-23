import { useState, useCallback, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import QuestionCard from './components/QuestionCard'
import PhaseTimeline from './components/PhaseTimeline'
import PhaseOutputPanel from './components/PhaseOutputPanel'
import DevTracePanel from './components/DevTracePanel'
import ResultPanel from './components/ResultPanel'
import StatusBar from './components/StatusBar'
import SettingsDialog from './components/SettingsDialog'
import { useSSE } from './hooks/useSSE'
import type {
  RunStatus, TraceRecord, PhaseId,
  ProjectSummary, ConversationSummary, ConversationTurn,
} from './types'
import { PHASES, PHASE_ICONS } from './types'

interface PhaseLog {
  phase: string
  summary: string
}

function newConvId(): string {
  return Math.random().toString(36).slice(2, 10)
}

export default function App() {
  const [conversationId, setConversationId] = useState(() => newConvId())
  const [projectId, setProjectId] = useState('')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [historyTurns, setHistoryTurns] = useState<ConversationTurn[]>([])

  const [runStatus, setRunStatus] = useState<RunStatus>('idle')
  const [activePhase, setActivePhase] = useState<PhaseId | null>(null)
  const [completedPhases, setCompletedPhases] = useState<Set<string>>(new Set())
  const [phaseLogs, setPhaseLogs] = useState<PhaseLog[]>([])
  const [phaseOutputs, setPhaseOutputs] = useState<TraceRecord[]>([])
  const [devTraces, setDevTraces] = useState<TraceRecord[]>([])
  const [result, setResult] = useState<{ summary: string; actions: string[] } | null>(null)
  const [devMode, setDevMode] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [loadingText, setLoadingText] = useState('')
  const [elapsed] = useState(0)

  const reset = useCallback(() => {
    setPhaseLogs([])
    setPhaseOutputs([])
    setDevTraces([])
    setResult(null)
    setActivePhase(null)
    setCompletedPhases(new Set())
    setLoadingText('')
  }, [])

  // ── 数据加载 ──────────────────────────
  const refreshProjects = useCallback(() => {
    fetch('/api/v1/projects')
      .then(r => r.json())
      .then(d => setProjects(d.projects || []))
      .catch(() => {})
  }, [])

  const refreshConversations = useCallback(() => {
    // project_id 始终携带（空串=默认项目），否则会返回全部对话
    fetch('/api/v1/conversations?project_id=' + encodeURIComponent(projectId))
      .then(r => r.json())
      .then(d => setConversations(d.conversations || []))
      .catch(() => {})
  }, [projectId])

  useEffect(() => { refreshProjects() }, [refreshProjects])
  useEffect(() => { refreshConversations() }, [refreshConversations])

  // ── 会话/项目切换 ─────────────────────
  const startNewConversation = useCallback(() => {
    reset()
    setHistoryTurns([])
    setConversationId(newConvId())
  }, [reset])

  const handleProjectChange = useCallback((pid: string) => {
    setProjectId(pid)
    reset()
    setHistoryTurns([])
    setConversationId(newConvId())
  }, [reset])

  const handleConversationSelect = useCallback(async (convId: string) => {
    reset()
    setConversationId(convId)
    try {
      const res = await fetch('/api/v1/conversations/' + encodeURIComponent(convId))
      const data = await res.json()
      setHistoryTurns(data.turns || [])
    } catch {
      setHistoryTurns([])
    }
  }, [reset])

  // ── SSE 回调 ──────────────────────────
  const handlePhase = useCallback((phase: string, summary: string) => {
    setActivePhase(phase as PhaseId)
    setCompletedPhases(prev => new Set([...prev, phase as PhaseId]))
    setPhaseLogs(prev => [...prev, { phase, summary }])
    setLoadingText(summary)
  }, [])

  const handleDone = useCallback((data: { summary: string; action_items: string[] }) => {
    setResult({ summary: data.summary, actions: data.action_items })
    setRunStatus('done')
    setActivePhase(null)
    setLoadingText('')
    // 新一轮已落库：刷新历史列表与项目统计
    refreshConversations()
    refreshProjects()
  }, [refreshConversations, refreshProjects])

  const handleTrace = useCallback((record: TraceRecord) => {
    setDevTraces(prev => [...prev, record])
    setPhaseOutputs(prev => [...prev, record])
  }, [])

  const handleTitle = useCallback((title: string, convId: string) => {
    setConversations(prev =>
      prev.map(c => (c.id === convId ? { ...c, name: title } : c)))
  }, [])

  const { start, stop } = useSSE({
    onPhase: handlePhase,
    onDone: handleDone,
    onTrace: devMode ? handleTrace : undefined,
    onTitle: handleTitle,
  })

  const handleRun = useCallback((
    question: string, context: string, mode: string, files: string[] = [],
  ) => {
    reset()
    setHistoryTurns([])
    setRunStatus('running')
    start(question, context, mode, conversationId, files, projectId)
  }, [reset, start, conversationId, projectId])

  const handleStop = useCallback(() => {
    stop()
    setRunStatus('idle')
  }, [stop])

  const showTimer = runStatus === 'running'

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        conversationId={conversationId}
        projectId={projectId}
        projects={projects}
        conversations={conversations}
        onProjectChange={handleProjectChange}
        onRefreshProjects={refreshProjects}
        onNewConversation={startNewConversation}
        onConversationSelect={handleConversationSelect}
        onSettingsClick={() => setShowSettings(true)}
      />

      {/* Divider */}
      <div className="w-px bg-linen/60 flex-shrink-0" />

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-3">
          {/* Question card */}
          <QuestionCard
            onRun={handleRun}
            onStop={handleStop}
            status={runStatus}
            projectId={projectId}
          />

          {/* 历史对话回看 */}
          {historyTurns.length > 0 && runStatus !== 'running' && (
            <div className="card p-4">
              <h3 className="text-xs font-semibold text-warmgray mb-3 uppercase tracking-wide">
                历史对话回看（{historyTurns.length} 轮）
              </h3>
              <div className="space-y-3">
                {historyTurns.map((t, i) => (
                  <div key={i} className="bg-paper rounded-lg border border-linen/40 p-3">
                    <div className="text-sm font-semibold text-ink mb-1">
                      问：{t.question}
                    </div>
                    {t.summary && t.summary !== '[...]' && (
                      <div className="text-sm text-warmgray leading-relaxed whitespace-pre-wrap">
                        {t.summary}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Phase timeline */}
          <PhaseTimeline
            activePhase={activePhase}
            completedPhases={completedPhases}
            loadingText={loadingText}
          />

          {/* Phase logs */}
          {phaseLogs.length > 0 && (
            <div className="card p-4">
              <h3 className="text-xs font-semibold text-warmgray mb-3 uppercase tracking-wide">
                认知过程
              </h3>
              <div className="space-y-2">
                {phaseLogs.map((log, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 bg-paper rounded-lg border border-linen/40"
                  >
                    <span className="text-lg flex-shrink-0 mt-0.5">
                      {PHASE_ICONS[log.phase] || '•'}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">
                        {log.phase in PHASE_ICONS
                          ? PHASES.find(p => p.id === log.phase)?.label ?? log.phase
                          : log.phase}
                      </div>
                      <div className="text-sm text-warmgray mt-0.5 leading-relaxed">
                        {log.summary}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Dev mode: phase intermediate outputs */}
          {devMode && phaseOutputs.length > 0 && (
            <PhaseOutputPanel records={phaseOutputs} />
          )}

          {/* Result */}
          {result && (
            <ResultPanel summary={result.summary} actions={result.actions} />
          )}

          {/* Dev mode: raw LLM traces */}
          {devMode && devTraces.length > 0 && (
            <DevTracePanel records={devTraces} />
          )}
        </div>

        {/* Status bar */}
        <StatusBar
          status={runStatus}
          conversationId={conversationId}
          devMode={devMode}
          onToggleDev={() => setDevMode(v => !v)}
          elapsed={elapsed}
          showTimer={showTimer}
        />
      </div>

      {/* Settings dialog */}
      {showSettings && (
        <SettingsDialog
          devMode={devMode}
          onSetDevMode={setDevMode}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}
