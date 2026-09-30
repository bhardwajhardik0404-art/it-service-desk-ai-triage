export type Role = 'employee' | 'agent' | 'admin'
export type User = { id: number; name: string; email: string; role: Role; team_id: number | null }
export type Team = { id: number; name: string; category: string; lead_user_id: number | null }
export type Ticket = {
  id: number; number: string; title: string; description: string; affected_service: string;
  impact: string; urgency: string; category: string; ai_suggested_priority: string | null;
  final_priority: string | null; triage_review_required: boolean; status: string;
  requester_id: number; requester_name: string; assigned_team_id: number | null;
  assigned_team_name: string | null; assigned_agent_id: number | null;
  assigned_agent_name: string | null; created_at: string; updated_at: string;
  first_response_at: string | null; resolved_at: string | null;
  response_due_at: string | null; resolution_due_at: string | null;
  response_breached_at: string | null; resolution_breached_at: string | null;
}
export type TicketDetail = Ticket & {
  comments: { id: number; body: string; is_internal: boolean; author_name: string; created_at: string }[];
  events: { id: number; event_type: string; detail: string; actor_name: string; created_at: string }[];
  ai_run: { category: string; priority: string; summary: string; reason: string; confidence: number; provider: string; model: string; status: string } | null;
}
export type Metrics = { total: number; active: number; resolved: number; breached: number; needs_review: number; categories: Record<string, number>; recent: Ticket[] }
export type Policy = { id: number; priority: string; response_minutes: number; resolution_minutes: number; calendar_mode: string }
export type Notice = { id: number; ticket_id: number; message: string; created_at: string; read_at: string | null }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const dateTime = (value: string | null) => value
  ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  : '—'

export const statusLabel = (status: string) => status.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())

