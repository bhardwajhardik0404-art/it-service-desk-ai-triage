import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  Activity, ArrowLeft, ArrowRight, Bell, CheckCircle2, ChevronDown, Clock3, Cpu,
  LayoutDashboard, LifeBuoy, LogOut, Plus, Search, Settings2, ShieldCheck,
  Ticket as TicketIcon, UserRound, Users, XCircle,
} from 'lucide-react'
import { api, dateTime, statusLabel, type Metrics, type Notice, type Policy, type Team, type Ticket, type TicketDetail, type User } from './api'

const DEMO = [
  { role: 'Employee', email: 'employee@demo.dev', note: 'Raise and follow tickets' },
  { role: 'Agent', email: 'agent@demo.dev', note: 'Work the Identity queue' },
  { role: 'Admin', email: 'admin@demo.dev', note: 'Manage rules and SLAs' },
]

const json = (body: unknown) => JSON.stringify(body)

function useLoad<T>(path: string | null, refresh = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!path) return
    let active = true
    api<T>(path).then(value => { if (active) { setData(value); setError('') } })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [path, refresh])
  return { data, error, setData }
}

function Badge({ value }: { value: string | null }) {
  const text = value ? statusLabel(value) : 'Pending'
  const key = (value || 'pending').toLowerCase().replaceAll('_', '-')
  return <span className={`badge badge-${key}`}>{text}</span>
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className="empty"><TicketIcon size={26} /><h3>{title}</h3><p>{detail}</p></div>
}

function ErrorBox({ message }: { message: string }) {
  return message ? <div className="error-box" role="alert"><XCircle size={16} />{message}</div> : null
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showDemo, setShowDemo] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    if (mode === 'register' && password !== confirmPassword) { setError('Passwords do not match'); setBusy(false); return }
    try { onLogin(await api<User>(mode === 'register' ? '/auth/register' : '/auth/login', { method: 'POST', body: json(mode === 'register' ? { name, email, password } : { email, password }) })) }
    catch (err) { setError((err as Error).message); if (mode === 'login') setPassword('') }
    finally { setBusy(false) }
  }
  return <div className="login-page">
    <div className="login-art">
      <div className="brand brand-light"><span className="brand-icon"><LifeBuoy size={23} /></span><span>DeskFlow</span></div>
      <div className="login-hero"><div className="eyebrow light">IT SERVICE MANAGEMENT</div><h1>Support requests,<br /><em>managed clearly.</em></h1>
        <p>Submit and track IT requests. Support teams can review triage suggestions, manage assignments, and monitor service deadlines.</p>
      </div>
      <div className="login-foot">DeskFlow · Service desk demonstration</div>
    </div>
    <div className="login-panel"><div className="login-form-wrap"><div className="eyebrow">ACCOUNT ACCESS</div><h2>{mode === 'login' ? 'Sign in' : 'Create employee account'}</h2>
      <p className="muted">{mode === 'login' ? 'Sign in with your account or use a demo account below.' : 'Create an account to raise and track your own IT requests.'}</p>
      <form onSubmit={submit} className="login-form">{mode === 'register' && <label>Full name<input value={name} onChange={e => setName(e.target.value)} autoComplete="name" required minLength={2} maxLength={100} /></label>}
        <label>Email address<input value={email} onChange={e => setEmail(e.target.value)} onBlur={() => setEmail(email.trim())} type="email" autoComplete="email" required /></label>
        <label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 10 : undefined} />{mode === 'register' && <small className="field-help">At least 10 characters, including a letter and a number.</small>}</label>
        {mode === 'register' && <label>Confirm password<input value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} type="password" autoComplete="new-password" required /></label>}
        <ErrorBox message={error} /><button className="button primary wide" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <ArrowRight size={17} /></button></form>
      <p className="auth-switch">{mode === 'login' ? 'New employee?' : 'Already have an account?'} <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); setPassword(''); setConfirmPassword('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>
      {mode === 'login' && <><button className="demo-toggle" type="button" aria-expanded={showDemo} onClick={() => setShowDemo(!showDemo)}>{showDemo ? 'Hide demo accounts' : 'Try demo accounts'}</button>
      {showDemo && <><div className="demo-heading">DEMO ACCOUNTS <span>password: Demo123!</span></div>
      <div className="demo-users">{DEMO.map(item => <button key={item.role} type="button" onClick={() => { setEmail(item.email); setPassword('Demo123!') }}>
        <span className="avatar small">{item.role[0]}</span><span><strong>{item.role}</strong><small>{item.note}</small></span><ArrowRight size={15} /></button>)}</div>
      </>}</>}
    </div></div>
  </div>
}

function Shell({ user, onLogout, children }: { user: User; onLogout: () => void; children: ReactNode }) {
  const location = useLocation()
  const [showNotices, setShowNotices] = useState(false)
  const [noticeRefresh, setNoticeRefresh] = useState(0)
  const { data: notices } = useLoad<Notice[]>('/notifications', noticeRefresh)
  const unread = notices?.filter(x => !x.read_at).length || 0
  const nav = [
    { to: '/', icon: LayoutDashboard, label: 'Overview' },
    { to: '/tickets', icon: TicketIcon, label: user.role === 'employee' ? 'My tickets' : 'Ticket queue' },
    ...(user.role === 'employee' ? [{ to: '/tickets/new', icon: Plus, label: 'New ticket' }] : []),
    ...(user.role === 'admin' ? [{ to: '/admin', icon: Settings2, label: 'Administration' }] : []),
    { to: '/account', icon: UserRound, label: 'My account' },
  ]
  const title = location.pathname === '/' ? 'Overview' : location.pathname.includes('/new') ? 'New ticket' :
    location.pathname === '/tickets' ? (user.role === 'employee' ? 'My tickets' : 'Ticket queue') :
      location.pathname === '/admin' ? 'Administration' : location.pathname === '/account' ? 'My account' : 'Ticket details'
  return <div className="app-shell">
    <aside className="sidebar"><Link className="brand" to="/"><span className="brand-icon"><LifeBuoy size={21} /></span><span>DeskFlow</span></Link>
      <div className="sidebar-label">WORKSPACE</div><nav aria-label="Main navigation">{nav.map(item => <Link key={item.to} className={`nav-item ${location.pathname === item.to ? 'active' : ''}`} to={item.to} aria-label={item.label} title={item.label}>
        <item.icon size={19} /><span>{item.label}</span></Link>)}</nav>
      <div className="sidebar-spacer" />
      <button className="sidebar-user" onClick={onLogout} title="Sign out" aria-label="Sign out"><span className="avatar">{user.name.split(' ').map(x => x[0]).join('').slice(0,2)}</span><span><strong>{user.name}</strong><small>{statusLabel(user.role)}</small></span><LogOut size={17} /></button>
    </aside>
    <div className="main-wrap"><header className="topbar"><div><span className="topbar-kicker">IT SERVICE DESK</span><h1>{title}</h1></div>
      <div className="topbar-actions"><span className="mode-pill"><span className="live-dot" /> {statusLabel(user.role)} workspace</span>
        <button className="mobile-signout" onClick={onLogout}><LogOut size={16} /> Sign out</button>
        <div className="notice-wrap"><button className="icon-button" title="Notifications" onClick={() => setShowNotices(!showNotices)}><Bell size={19} />{unread > 0 && <i />}</button>
          {showNotices && <div className="notice-pop"><div className="notice-head"><strong>Notifications</strong><span>{unread} unread</span></div>
            {(notices || []).length ? notices!.map(n => <button key={n.id} className={`notice-item ${!n.read_at ? 'unread' : ''}`} onClick={async () => { await api(`/notifications/${n.id}/read`, { method: 'POST' }); setNoticeRefresh(x => x+1); setShowNotices(false); window.location.href = `/tickets/${n.ticket_id}` }}><span>{n.message}</span><small>{dateTime(n.created_at)}</small></button>) : <p className="notice-empty">No notifications yet.</p>}
          </div>}</div></div></header><main className="content">{children}</main></div>
  </div>
}

function Dashboard({ user }: { user: User }) {
  const { data, error } = useLoad<Metrics>('/dashboard/metrics')
  const totalCategories = Object.values(data?.categories || {}).reduce((a,b) => a+b, 0) || 1
  return <><div className="page-intro"><div><div className="eyebrow">{statusLabel(user.role).toUpperCase()} WORKSPACE</div><h2>Service desk overview</h2><p>Current ticket activity, workload, and service performance.</p></div>
    {user.role === 'employee' ? <Link className="button primary" to="/tickets/new"><Plus size={17} /> Raise a ticket</Link> : <Link className="button primary" to="/tickets"><TicketIcon size={17} /> View queue</Link>}</div>
    <ErrorBox message={error} />
    <div className="stat-grid">
      <Stat icon={<TicketIcon size={21} />} label="Total tickets" value={data?.total} note="All visible tickets" tone="blue" />
      <Stat icon={<Activity size={21} />} label="Active" value={data?.active} note="In progress or awaiting work" tone="teal" />
      <Stat icon={<CheckCircle2 size={21} />} label="Resolved" value={data?.resolved} note="Completed requests" tone="green" />
      <Stat icon={<Clock3 size={21} />} label="SLA breaches" value={data?.breached} note="Need attention" tone="amber" />
    </div>
    <div className="dashboard-grid"><section className="panel"><div className="panel-title"><div><h3>Recent tickets</h3></div><Link to="/tickets" className="text-link">View all <ArrowRight size={15} /></Link></div>
      <div className="recent-list">{data?.recent?.length ? data.recent.map(t => <Link className="recent-row" key={t.id} to={`/tickets/${t.id}`}><span className="ticket-icon"><TicketIcon size={17} /></span><span className="recent-main"><strong>{t.title}</strong><small>{t.number} · {t.assigned_team_name || 'Unassigned'}</small></span><Badge value={t.status} /></Link>) : <Empty title="No tickets yet" detail="New requests will appear here." />}</div></section>
      <section className="panel"><div className="panel-title"><div><h3>Tickets by category</h3></div><Cpu size={19} className="muted-icon" /></div>
        <div className="category-list">{['ACCESS','SOFTWARE','HARDWARE','OTHER'].map((name,i) => { const count = data?.categories[name] || 0; return <div className="category-row" key={name}><div><span className={`category-dot dot-${i}`} /> <strong>{statusLabel(name)}</strong><span>{count}</span></div><div className="bar"><div style={{width:`${count/totalCategories*100}%`}} /></div></div> })}</div>
        <div className="insight-card"><span><strong>{data?.needs_review || 0} tickets need triage review</strong><small>Suggestions awaiting a human decision.</small></span></div>
      </section></div></>
}

function Stat({ icon, label, value, note, tone }: { icon: ReactNode; label: string; value?: number; note: string; tone: string }) {
  return <div className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><div className="stat-value">{value ?? '—'}</div><strong>{label}</strong><small>{note}</small></div>
}

function TicketList({ user }: { user: User }) {
  const { data, error } = useLoad<Ticket[]>('/tickets')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('ALL')
  const [category, setCategory] = useState('ALL')
  const filtered = (data || []).filter(t =>
    (status === 'ALL' || t.status === status) && (category === 'ALL' || t.category === category) &&
    `${t.title} ${t.number} ${t.requester_name}`.toLowerCase().includes(query.toLowerCase()))
  return <><div className="page-intro compact"><div><div className="eyebrow">TICKET MANAGEMENT</div><h2>{user.role === 'employee' ? 'Your requests' : 'Support queue'}</h2><p>{user.role === 'employee' ? 'Track every request from submission to resolution.' : 'Prioritize work, review AI decisions, and keep SLAs on track.'}</p></div>
    {user.role === 'employee' && <Link className="button primary" to="/tickets/new"><Plus size={17} /> New ticket</Link>}</div>
    <ErrorBox message={error} /><section className="panel table-panel"><div className="filterbar"><div className="search-box"><Search size={17} /><input placeholder="Search tickets..." value={query} onChange={e => setQuery(e.target.value)} /></div>
      <select value={status} onChange={e => setStatus(e.target.value)}><option value="ALL">All statuses</option>{['NEW','TRIAGING','OPEN','IN_PROGRESS','WAITING_FOR_EMPLOYEE','ESCALATED','RESOLVED','CLOSED'].map(x => <option key={x}>{x}</option>)}</select>
      <select value={category} onChange={e => setCategory(e.target.value)}><option value="ALL">All categories</option>{['HARDWARE','SOFTWARE','ACCESS','OTHER'].map(x => <option key={x}>{x}</option>)}</select></div>
      <div className="table-scroll"><table className="ticket-table"><thead><tr><th>Ticket</th><th>Category</th><th>Priority</th><th>Status</th><th>Assigned team</th><th>Created</th><th></th></tr></thead><tbody>
        {filtered.map(t => <tr key={t.id}><td><Link to={`/tickets/${t.id}`} className="table-ticket"><strong>{t.title}</strong><small>{t.number} · {t.requester_name}</small></Link></td><td>{statusLabel(t.category)}</td><td><Badge value={t.final_priority} /></td><td><Badge value={t.status} /></td><td>{t.assigned_team_name || 'Awaiting triage'}</td><td>{dateTime(t.created_at)}</td><td><Link className="row-arrow" to={`/tickets/${t.id}`}><ArrowRight size={17} /></Link></td></tr>)}</tbody></table></div>
      {!filtered.length && <Empty title="No matching tickets" detail="Try a different filter or create a new request." />}
    </section></>
}

function NewTicket() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ title: '', description: '', affected_service: '', impact: 'individual', urgency: 'normal' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try { const result = await api<Ticket>('/tickets', { method: 'POST', body: json({ ...form, affected_service: form.affected_service || 'General IT' }) }); navigate(`/tickets/${result.id}`) }
    catch (err) { setError((err as Error).message); setBusy(false) }
  }
  return <><div className="page-intro compact"><div><div className="eyebrow">EMPLOYEE PORTAL</div><h2>Tell us what happened.</h2><p>Include enough detail for the right team to start helping quickly.</p></div></div>
    <div className="form-layout"><form className="panel create-panel" onSubmit={submit}><h3>Request details</h3><p className="muted">Your ticket will be saved immediately. AI triage runs after submission.</p>
      <label>Short title <span>*</span><input required minLength={5} maxLength={180} placeholder="e.g. Cannot access payroll application" value={form.title} onChange={e => setForm({...form,title:e.target.value})} /></label>
      <label>Describe the issue <span>*</span><textarea required minLength={10} rows={6} placeholder="What were you trying to do? What error did you see? Who is affected?" value={form.description} onChange={e => setForm({...form,description:e.target.value})} /></label>
      <label>Affected service<input placeholder="e.g. Payroll, VPN, laptop" value={form.affected_service} onChange={e => setForm({...form,affected_service:e.target.value})} /></label>
      <div className="two-cols"><label>Impact<select value={form.impact} onChange={e => setForm({...form,impact:e.target.value})}><option value="individual">Only me</option><option value="team">My team</option><option value="company">Company-wide</option></select></label>
      <label>Urgency<select value={form.urgency} onChange={e => setForm({...form,urgency:e.target.value})}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="critical">Critical</option></select></label></div>
      <ErrorBox message={error} /><div className="form-actions"><Link to="/tickets" className="button secondary">Cancel</Link><button className="button primary" disabled={busy}>{busy ? 'Creating…' : 'Create ticket'} <ArrowRight size={17} /></button></div>
    </form><aside className="help-panel"><h3>After you submit</h3><ol><li>Your request receives a ticket number.</li><li>Triage suggests a category and priority.</li><li>Routing rules assign a support team.</li><li>You can track progress and reply at any time.</li></ol></aside></div></>
}

function TicketPage({ user }: { user: User }) {
  const { id } = useParams()
  const staff = user.role !== 'employee'
  const [refresh, setRefresh] = useState(0)
  const { data: ticket, error } = useLoad<TicketDetail>(`/tickets/${id}`, refresh)
  const { data: teams } = useLoad<Team[]>('/teams')
  const { data: agents } = useLoad<User[]>(staff ? '/users' : null)
  const [comment, setComment] = useState('')
  const [internal, setInternal] = useState(false)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!ticket || !(['NEW', 'TRIAGING'].includes(ticket.status) && !ticket.ai_run)) return
    const timer = window.setInterval(() => setRefresh(x => x + 1), 2500)
    return () => window.clearInterval(timer)
  }, [ticket?.status, ticket?.ai_run])
  async function action(path: string, value: unknown) {
    setBusy(true); setActionError('')
    try { await api(`/tickets/${id}/${path}`, { method: 'PATCH', body: json(value) }); setRefresh(x => x+1) }
    catch (err) { setActionError((err as Error).message) }
    finally { setBusy(false) }
  }
  async function submitComment(e: FormEvent) {
    e.preventDefault(); setBusy(true); setActionError('')
    try { await api(`/tickets/${id}/comments`, { method: 'POST', body: json({ body: comment, is_internal: internal }) }); setComment(''); setRefresh(x => x+1) }
    catch (err) { setActionError((err as Error).message) }
    finally { setBusy(false) }
  }
  if (error) return <ErrorBox message={error} />
  if (!ticket) return <div className="loading">Loading ticket…</div>
  const options = ticket.status === 'TRIAGING' ? ['OPEN','IN_PROGRESS'] : ticket.status === 'OPEN' ? ['IN_PROGRESS','WAITING_FOR_EMPLOYEE','RESOLVED'] :
    ticket.status === 'IN_PROGRESS' ? ['WAITING_FOR_EMPLOYEE','RESOLVED','OPEN'] : ticket.status === 'WAITING_FOR_EMPLOYEE' ? ['IN_PROGRESS','RESOLVED'] :
      ticket.status === 'ESCALATED' ? ['IN_PROGRESS','WAITING_FOR_EMPLOYEE','RESOLVED'] : ticket.status === 'RESOLVED' ? ['CLOSED','OPEN'] : []
  return <><Link to="/tickets" className="back-link"><ArrowLeft size={16} /> Back to tickets</Link>
    <div className="detail-heading"><div><div className="eyebrow">{ticket.number} · {dateTime(ticket.created_at)}</div><h2>{ticket.title}</h2><div className="heading-badges"><Badge value={ticket.status} /><Badge value={ticket.final_priority} /><span className="plain-chip">{statusLabel(ticket.category)}</span></div></div>
      {staff && options.length > 0 && <div className="status-select"><select aria-label="Change status" value="" onChange={e => action('status', { status: e.target.value })} disabled={busy}><option value="">Change status</option>{options.map(x => <option key={x} value={x}>{statusLabel(x)}</option>)}</select><ChevronDown size={16} /></div>}
      {!staff && ticket.status === 'RESOLVED' && <button className="button secondary" onClick={() => action('status',{status:'OPEN'})}>Reopen ticket</button>}
    </div><ErrorBox message={actionError} />
    <div className="detail-grid"><div className="detail-main"><section className="panel detail-card"><div className="section-head"><h3>Request details</h3><span>Submitted by {ticket.requester_name}</span></div><p className="description">{ticket.description}</p>
      <div className="detail-facts"><div><small>AFFECTED SERVICE</small><strong>{ticket.affected_service}</strong></div><div><small>IMPACT</small><strong>{statusLabel(ticket.impact)}</strong></div><div><small>URGENCY</small><strong>{statusLabel(ticket.urgency)}</strong></div></div></section>
      <section className="panel detail-card"><div className="section-head"><h3>Conversation</h3><span>{ticket.comments.length} messages</span></div>
        <div className="conversation">{ticket.comments.length ? ticket.comments.map(c => <div className={`message ${c.is_internal ? 'internal' : ''}`} key={c.id}><div className="message-avatar">{c.author_name[0]}</div><div><div className="message-meta"><strong>{c.author_name}</strong>{c.is_internal && <span>Internal note</span>}<small>{dateTime(c.created_at)}</small></div><p>{c.body}</p></div></div>) : <p className="muted">No replies yet. Start the conversation below.</p>}</div>
        {ticket.status !== 'CLOSED' && <form onSubmit={submitComment} className="comment-form"><textarea required placeholder={internal ? 'Add a note visible only to agents…' : 'Write a reply…'} value={comment} onChange={e => setComment(e.target.value)} rows={3} />
          <div>{staff && <label className="check-label"><input type="checkbox" checked={internal} onChange={e => setInternal(e.target.checked)} /> Internal note</label>}<button className="button primary" disabled={busy || !comment.trim()}>Post {internal ? 'note' : 'reply'} <ArrowRight size={16} /></button></div></form>}</section>
      <section className="panel detail-card"><div className="section-head"><h3>Activity timeline</h3><span>Every change recorded</span></div><div className="timeline">{ticket.events.map(item => <div key={item.id} className="timeline-item"><span className="timeline-dot" /><div><strong>{statusLabel(item.event_type)}</strong><p>{item.detail}</p><small>{item.actor_name} · {dateTime(item.created_at)}</small></div></div>)}</div></section>
    </div><aside className="detail-aside">
      {staff && <section className="panel ai-panel"><div className="ai-title"><div><div className="eyebrow">AUTOMATED SUGGESTION</div><h3>AI triage</h3></div></div>
        {ticket.ai_run ? <><p>{ticket.ai_run.summary || 'No summary available.'}</p><div className="ai-grid"><div><small>CATEGORY</small><strong>{statusLabel(ticket.ai_run.category || 'Other')}</strong></div><div><small>PRIORITY</small><strong>{ticket.ai_run.priority || '—'}</strong></div><div><small>CONFIDENCE</small><strong>{ticket.ai_run.confidence == null ? '—' : `${Math.round(ticket.ai_run.confidence*100)}%`}</strong></div></div>
          <div className="ai-reason">{ticket.ai_run.reason}</div><div className="ai-foot"><span>{ticket.ai_run.provider === 'demo' ? 'Demo rules' : 'OpenAI model'}</span><span>{ticket.triage_review_required ? 'Review required' : 'Applied'}</span></div></> : <p className="muted">Triage is pending. Refresh in a moment.</p>}
      </section>}
      <section className="panel side-panel"><h3>Assignment & priority</h3><div className="side-row"><span>Team</span><strong>{ticket.assigned_team_name || 'Unassigned'}</strong></div><div className="side-row"><span>Agent</span><strong>{ticket.assigned_agent_name || 'Not assigned'}</strong></div>
        {staff && <div className="controls"><label>Category<select value={ticket.category} onChange={e => action('category',{category:e.target.value})} disabled={busy}>{['HARDWARE','SOFTWARE','ACCESS','OTHER'].map(x => <option key={x}>{x}</option>)}</select></label>
          <label>Priority<select value={ticket.final_priority || ''} onChange={e => action('priority',{priority:e.target.value})} disabled={busy}><option value="" disabled>Select</option>{['P1','P2','P3','P4'].map(x => <option key={x}>{x}</option>)}</select></label>
          <label>Team<select value={ticket.assigned_team_id || ''} onChange={e => action('assignment',{team_id:Number(e.target.value)})} disabled={busy}><option value="" disabled>Select</option>{(teams || []).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
          {ticket.assigned_team_id && <label>Agent<select value={ticket.assigned_agent_id || ''} onChange={e => action('assignment',{team_id:ticket.assigned_team_id,agent_id:e.target.value ? Number(e.target.value) : null})} disabled={busy}><option value="">Unassigned</option>{(agents || []).filter(a => a.team_id === ticket.assigned_team_id).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}</div>}
      </section>
      <section className="panel side-panel"><h3>SLA commitments</h3><div className="sla-row"><div><small>FIRST RESPONSE</small><strong>{dateTime(ticket.response_due_at)}</strong></div>{ticket.first_response_at ? <CheckCircle2 size={19} className="green-text" /> : ticket.response_breached_at ? <XCircle size={19} className="red-text" /> : <Clock3 size={19} className="blue-text" />}</div>
        <div className="sla-row"><div><small>RESOLUTION</small><strong>{dateTime(ticket.resolution_due_at)}</strong></div>{ticket.resolved_at ? <CheckCircle2 size={19} className="green-text" /> : ticket.resolution_breached_at ? <XCircle size={19} className="red-text" /> : <Clock3 size={19} className="blue-text" />}</div>
        <p className="sla-note">Deadlines use the configured support calendar. Public agent replies count as first response.</p></section>
    </aside></div></>
}

function Account({ user }: { user: User }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage('')
    if (newPassword !== confirmPassword) { setError('New passwords do not match'); return }
    setBusy(true)
    try {
      await api('/auth/change-password', { method: 'POST', body: json({ current_password: currentPassword, new_password: newPassword }) })
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); setMessage('Password updated. Other sessions have been signed out.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <><div className="page-intro compact"><div><div className="eyebrow">ACCOUNT</div><h2>My account</h2><p>View your account details and update your password.</p></div></div>
    <div className="account-layout"><section className="panel account-panel"><h3>Account details</h3><div className="account-detail"><span>Name</span><strong>{user.name}</strong></div><div className="account-detail"><span>Email</span><strong>{user.email}</strong></div><div className="account-detail"><span>Role</span><strong>{statusLabel(user.role)}</strong></div></section>
    <form className="panel account-panel login-form" onSubmit={submit}><h3>Change password</h3><p className="muted">Use at least 10 characters. Changing your password ends your other sessions.</p>
      <label>Current password<input type="password" autoComplete="current-password" required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} /></label>
      <label>New password<input type="password" autoComplete="new-password" required minLength={10} value={newPassword} onChange={e => setNewPassword(e.target.value)} /><small className="field-help">At least 10 characters, including a letter and a number.</small></label>
      <label>Confirm new password<input type="password" autoComplete="new-password" required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></label>
      <ErrorBox message={error} />{message && <div className="success-box"><CheckCircle2 size={16} />{message}</div>}
      <button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Update password'}</button></form></div></>
}

function CreateAgent({ teams, onCreated }: { teams: Team[]; onCreated: () => void }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', team_id: '' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const result = await api<User>('/admin/agents', { method: 'POST', body: json({ ...form, team_id: Number(form.team_id) }) })
      setMessage(`${result.name} can now sign in with the email and password you set.`)
      setForm({ name: '', email: '', password: '', team_id: '' }); onCreated()
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="panel admin-panel agent-account-panel"><div className="panel-title"><div><h3>Create agent account</h3></div><UserRound size={20} className="muted-icon" /></div>
    <p className="muted">Agents are created by an admin and assigned to a support team. Give the initial password to the agent privately; they can change it from My account.</p>
    <form className="agent-form" onSubmit={submit}><label>Full name<input required minLength={2} maxLength={100} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
      <label>Email<input required type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>
      <label>Support team<select required value={form.team_id} onChange={e => setForm({ ...form, team_id: e.target.value })}><option value="">Select a team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>
      <label>Initial password<input required type="password" minLength={10} autoComplete="new-password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /><small className="field-help">At least 10 characters, including a letter and a number.</small></label>
      <ErrorBox message={error} />{message && <div className="success-box"><CheckCircle2 size={16} />{message}</div>}
      <button className="button primary" disabled={busy || !teams.length}>{busy ? 'Creating…' : 'Create agent'}</button></form></section>
}

function Admin() {
  const [refresh, setRefresh] = useState(0)
  const { data: policies, error } = useLoad<Policy[]>('/admin/sla-policies', refresh)
  const { data: teams } = useLoad<Team[]>('/teams', refresh)
  const { data: staff } = useLoad<User[]>('/users', refresh)
  const [message, setMessage] = useState('')
  const [errorAction, setErrorAction] = useState('')
  async function savePolicy(policy: Policy) {
    try { await api(`/admin/sla-policies/${policy.id}`, { method: 'PATCH', body: json({response_minutes:policy.response_minutes,resolution_minutes:policy.resolution_minutes,calendar_mode:policy.calendar_mode}) }); setMessage(`${policy.priority} policy saved`); setErrorAction(''); setRefresh(x => x+1) }
    catch (err) { setErrorAction((err as Error).message) }
  }
  async function runCheck() {
    try { const result = await api<{escalated:number}>('/admin/run-sla-check', {method:'POST'}); setMessage(`SLA check complete: ${result.escalated} ticket(s) escalated`); setErrorAction('') }
    catch (err) { setErrorAction((err as Error).message) }
  }
  async function saveTeam(team: Team) {
    try { await api(`/admin/teams/${team.id}`, { method: 'PATCH', body: json({name:team.name,lead_user_id:team.lead_user_id}) }); setMessage(`${team.name} saved`); setErrorAction(''); setRefresh(x => x+1) }
    catch (err) { setErrorAction((err as Error).message) }
  }
  return <><div className="page-intro compact"><div><div className="eyebrow">CONFIGURATION</div><h2>Service desk settings</h2><p>Keep routing and service commitments clear and transparent.</p></div></div>
    <ErrorBox message={error || errorAction} />{message && <div className="success-box"><CheckCircle2 size={16} />{message}</div>}
    <div className="admin-grid"><section className="panel admin-panel"><div className="panel-title"><div><div className="eyebrow">ROUTING</div><h3>Support teams</h3></div><Users size={20} className="muted-icon" /></div>
      <p className="muted">AI chooses a category. The backend routes it to the mapped team. Edit the team label and escalation lead here.</p><div className="team-list">{teams?.map(team => <TeamEditor key={team.id} initial={team} staff={staff || []} save={saveTeam} />)}</div></section>
      <section className="panel admin-panel"><div className="panel-title"><div><div className="eyebrow">SERVICE LEVELS</div><h3>SLA policies</h3></div><Clock3 size={20} className="muted-icon" /></div><p className="muted">Time targets are in minutes. Business mode counts 09:00–17:00, Monday–Friday.</p>
        <div className="policy-list">{policies?.map(policy => <PolicyEditor key={policy.id} initial={policy} save={savePolicy} />)}</div></section></div>
    <CreateAgent teams={teams || []} onCreated={() => setRefresh(x => x+1)} />
    <section className="panel admin-panel admin-utility"><div><div className="eyebrow">DEMO CONTROL</div><h3>Run SLA check now</h3><p className="muted">Docker mode checks every minute. Run this check now to demonstrate escalation immediately.</p></div><button className="button secondary" onClick={runCheck}>Check deadlines <ArrowRight size={16} /></button></section></>
}

function PolicyEditor({ initial, save }: { initial: Policy; save: (p: Policy) => void }) {
  const [policy, setPolicy] = useState(initial)
  return <div className="policy-row"><strong>{policy.priority}</strong><label>Response<input type="number" min={1} value={policy.response_minutes} onChange={e => setPolicy({...policy,response_minutes:Number(e.target.value)})} /></label>
    <label>Resolution<input type="number" min={1} value={policy.resolution_minutes} onChange={e => setPolicy({...policy,resolution_minutes:Number(e.target.value)})} /></label>
    <label>Calendar<select value={policy.calendar_mode} onChange={e => setPolicy({...policy,calendar_mode:e.target.value})}><option value="business">Business</option><option value="always">24/7</option></select></label>
    <button className="button mini" onClick={() => save(policy)}>Save</button></div>
}

function TeamEditor({ initial, staff, save }: { initial: Team; staff: User[]; save: (t: Team) => void }) {
  const [team, setTeam] = useState(initial)
  return <div className="team-editor"><span className="team-icon"><ShieldCheck size={17} /></span><div><small>{statusLabel(team.category)} TICKETS</small>
    <input aria-label={`${team.category} team name`} value={team.name} onChange={e => setTeam({...team,name:e.target.value})} />
    <select aria-label={`${team.category} team lead`} value={team.lead_user_id || ''} onChange={e => setTeam({...team,lead_user_id:e.target.value ? Number(e.target.value) : null})}><option value="">No lead</option>{staff.filter(u => u.role === 'admin' || u.team_id === team.id).map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
  </div><button className="button mini" onClick={() => save(team)}>Save</button></div>
}

export default function App() {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { api<User>('/auth/me').then(setUser).catch(() => {}).finally(() => setLoading(false)) }, [])
  async function logout() { await api('/auth/logout', { method: 'POST' }).catch(() => {}); setUser(null); navigate('/') }
  if (loading) return <div className="loading full"><LifeBuoy size={28} /> Loading DeskFlow…</div>
  if (!user) return <Login onLogin={setUser} />
  return <Shell user={user} onLogout={logout}><Routes>
    <Route path="/" element={<Dashboard user={user} />} />
    <Route path="/tickets" element={<TicketList user={user} />} />
    <Route path="/tickets/new" element={user.role === 'employee' ? <NewTicket /> : <Navigate to="/tickets" />} />
    <Route path="/tickets/:id" element={<TicketPage user={user} />} />
    <Route path="/admin" element={user.role === 'admin' ? <Admin /> : <Navigate to="/" />} />
    <Route path="/account" element={<Account user={user} />} />
    <Route path="*" element={<Navigate to="/" />} />
  </Routes></Shell>
}

