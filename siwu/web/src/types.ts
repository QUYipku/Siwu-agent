// ── Cognitive phases ──────────────────
export const PHASES = [
  { id: 'investigation', icon: '\u{1f50d}', label: '调查研究', subtitle: '实事求是' },
  { id: 'contradiction',  icon: '⚡', label: '矛盾分析', subtitle: '抓主要矛盾' },
  { id: 'rational',       icon: '\u{1f9e0}', label: '理性认识', subtitle: '去伪存真' },
  { id: 'decision',       icon: '\u{1f3af}', label: '决策输出', subtitle: '战略战术' },
  { id: 'practice',       icon: '⚙️', label: '实践检验', subtitle: '检验真理' },
  { id: 'reflection',     icon: '\u{1f504}', label: '反思复盘', subtitle: '总结提升' },
] as const

export type PhaseId = typeof PHASES[number]['id']

export const PHASE_LABELS: Record<string, string> = {}
export const PHASE_ICONS: Record<string, string> = {}
for (const p of PHASES) {
  PHASE_LABELS[p.id] = p.label
  PHASE_ICONS[p.id] = p.icon
}

// ── SSE event ─────────────────────────
export interface SSEPhaseEvent {
  phase: string
  summary: string
}

export interface SSEDoneEvent {
  done: true
  summary: string
  action_items: string[]
  session_id: string
  conversation_id?: string
  project_id?: string
}

// ── Projects & conversations ──────────
export interface ProjectSummary {
  id: string
  name: string
  workspace_dir: string
  data_dir?: string
  conversation_count: number
  last_active: string
}

export interface ConversationSummary {
  id: string
  name: string
  question_count: number
  last_question: string
  last_active: string
}

export interface ConversationTurn {
  session_id: string
  question: string
  summary: string
  action_items: string[]
  created_at: string
}

export interface ConversationDetail {
  conversation_id: string
  name: string
  turns: ConversationTurn[]
}

export interface TraceRecord {
  phase: string
  tag: string
  output: string
  seq: number
}

// ── API response types ────────────────
export interface RunResponse {
  session_id: string
  conversation_id: string
  summary: string
  action_items: string[]
  principal_contradiction: string
  convergence_score: number
  iterations: number
  phase_durations: Record<string, number>
}

export interface TraceEpisode {
  session_id: string
  conversation_id: string
  question: string
  summary: string
  created_at: string
}

// ── App state ─────────────────────────
export type RunStatus = 'idle' | 'running' | 'done' | 'error'
