from collections import Counter
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, hash_password, make_token, require_admin, require_staff, verify_password
from .config import get_settings
from .database import get_db
from .jobs import check_sla_now, event, triage_ticket, triage_ticket_now
from .models import AITriageRun, Comment, Notification, SLAPolicy, Team, Ticket, TicketEvent, User
from .sla import apply_sla, aware_utc, deadline, extend_waiting_sla


app = FastAPI(title="Service Desk with AI Triage", version="1.0.0")
CATEGORIES = {"HARDWARE", "SOFTWARE", "ACCESS", "OTHER"}
PRIORITIES = {"P1", "P2", "P3", "P4"}
STATUSES = {"NEW", "TRIAGING", "OPEN", "IN_PROGRESS", "WAITING_FOR_EMPLOYEE", "ESCALATED", "RESOLVED", "CLOSED"}


class LoginInput(BaseModel):
    email: str
    password: str


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)


class AgentInput(RegisterInput):
    team_id: int


class PasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class TicketInput(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    description: str = Field(min_length=10, max_length=5000)
    affected_service: str = Field(default="General IT", max_length=100)
    impact: str = Field(default="individual", pattern="^(individual|team|company)$")
    urgency: str = Field(default="normal", pattern="^(low|normal|high|critical)$")


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    is_internal: bool = False


class StatusInput(BaseModel):
    status: str


class AssignmentInput(BaseModel):
    team_id: int
    agent_id: int | None = None


class PriorityInput(BaseModel):
    priority: str


class CategoryInput(BaseModel):
    category: str


class TeamInput(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    lead_user_id: int | None = None


class PolicyInput(BaseModel):
    response_minutes: int = Field(gt=0, le=43200)
    resolution_minutes: int = Field(gt=0, le=43200)
    calendar_mode: str = Field(pattern="^(business|always)$")


def user_data(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "team_id": user.team_id}


def stamp(value: datetime | None) -> str | None:
    return aware_utc(value).isoformat() if value else None


def ticket_data(db: Session, ticket: Ticket) -> dict:
    team = db.get(Team, ticket.assigned_team_id) if ticket.assigned_team_id else None
    requester = db.get(User, ticket.requester_id)
    agent = db.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
    return {
        "id": ticket.id, "number": ticket.number, "title": ticket.title, "description": ticket.description,
        "affected_service": ticket.affected_service, "impact": ticket.impact, "urgency": ticket.urgency,
        "category": ticket.category, "ai_suggested_priority": ticket.ai_suggested_priority,
        "final_priority": ticket.final_priority, "triage_review_required": ticket.triage_review_required,
        "status": ticket.status, "requester_id": ticket.requester_id,
        "requester_name": requester.name if requester else "Unknown",
        "assigned_team_id": ticket.assigned_team_id, "assigned_team_name": team.name if team else None,
        "assigned_agent_id": ticket.assigned_agent_id, "assigned_agent_name": agent.name if agent else None,
        "created_at": stamp(ticket.created_at), "updated_at": stamp(ticket.updated_at),
        "first_response_at": stamp(ticket.first_response_at), "resolved_at": stamp(ticket.resolved_at),
        "response_due_at": stamp(ticket.response_due_at), "resolution_due_at": stamp(ticket.resolution_due_at),
        "response_breached_at": stamp(ticket.response_breached_at),
        "resolution_breached_at": stamp(ticket.resolution_breached_at),
    }


def accessible_ticket(db: Session, ticket_id: int, user: User) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.role == "employee" and ticket.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.role == "agent" and ticket.assigned_team_id not in {user.team_id, None} and ticket.assigned_agent_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(body: LoginInput, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response.set_cookie("desk_session", make_token(user), httponly=True, secure=get_settings().cookie_secure,
                        samesite="lax", max_age=8*3600, path="/")
    return user_data(user)


@app.post("/api/auth/register", status_code=201)
def register(body: RegisterInput, response: Response, db: Session = Depends(get_db)) -> dict:
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must contain at least 2 characters")
    user = User(name=name, email=body.email.lower().strip(),
                password_hash=hash_password(body.password), role="employee")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    db.refresh(user)
    response.set_cookie("desk_session", make_token(user), httponly=True, secure=get_settings().cookie_secure,
                        samesite="lax", max_age=8*3600, path="/")
    return user_data(user)


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("desk_session", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_data(user)


@app.post("/api/auth/change-password")
def change_password(body: PasswordInput, response: Response, db: Session = Depends(get_db),
                    user: User = Depends(current_user)) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Choose a different password")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    response.set_cookie("desk_session", make_token(user), httponly=True, secure=get_settings().cookie_secure,
                        samesite="lax", max_age=8*3600, path="/")
    return {"ok": True}


@app.post("/api/admin/agents", status_code=201)
def create_agent(body: AgentInput, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must contain at least 2 characters")
    if not db.get(Team, body.team_id):
        raise HTTPException(status_code=404, detail="Support team not found")
    user = User(name=name, email=body.email.lower().strip(),
                password_hash=hash_password(body.password), role="agent", team_id=body.team_id)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    db.refresh(user)
    return user_data(user)


@app.get("/api/users")
def users(db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[dict]:
    query = select(User).where(User.role.in_(["agent", "admin"]))
    if user.role == "agent":
        query = query.where(User.team_id == user.team_id)
    return [user_data(item) for item in db.scalars(query.order_by(User.name))]


@app.get("/api/teams")
def teams(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    return [{"id": x.id, "name": x.name, "category": x.category, "lead_user_id": x.lead_user_id}
            for x in db.scalars(select(Team).order_by(Team.name))]


@app.post("/api/tickets", status_code=201)
def create_ticket(body: TicketInput, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    ticket = Ticket(requester_id=user.id, title=body.title.strip(),
                    description=body.description.strip(), affected_service=body.affected_service.strip(),
                    impact=body.impact, urgency=body.urgency, status="NEW")
    db.add(ticket)
    db.flush()
    ticket.number = f"INC-{ticket.id:05d}"
    event(db, ticket.id, "CREATED", f"Ticket created by {user.name}", user.id)
    db.commit()
    if get_settings().sync_jobs:
        background.add_task(triage_ticket_now, ticket.id)
    else:
        try:
            triage_ticket.delay(ticket.id)
        except Exception:
            ticket.status = "TRIAGING"
            ticket.triage_review_required = True
            event(db, ticket.id, "QUEUE_FAILED", "AI job queue unavailable; manual review required")
            db.commit()
    return ticket_data(db, ticket)


@app.get("/api/tickets")
def list_tickets(status: str | None = None, category: str | None = None, priority: str | None = None,
                 db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    query = select(Ticket)
    if user.role == "employee":
        query = query.where(Ticket.requester_id == user.id)
    elif user.role == "agent":
        query = query.where((Ticket.assigned_team_id == user.team_id) | (Ticket.assigned_team_id.is_(None)) | (Ticket.assigned_agent_id == user.id))
    if status:
        query = query.where(Ticket.status == status)
    if category:
        query = query.where(Ticket.category == category)
    if priority:
        query = query.where(Ticket.final_priority == priority)
    tickets = db.scalars(query.order_by(desc(Ticket.created_at)).limit(200)).all()
    return [ticket_data(db, x) for x in tickets]


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    result = ticket_data(db, ticket)
    comments = db.scalars(select(Comment).where(Comment.ticket_id == ticket.id).order_by(Comment.created_at)).all()
    events = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.created_at)).all()
    run = db.scalar(select(AITriageRun).where(AITriageRun.ticket_id == ticket.id).order_by(desc(AITriageRun.id)))
    result["comments"] = [{"id": x.id, "body": x.body, "is_internal": x.is_internal,
                            "created_at": stamp(x.created_at), "author_name": db.get(User, x.author_id).name}
                           for x in comments if user.role != "employee" or not x.is_internal]
    result["events"] = [{"id": x.id, "event_type": x.event_type, "detail": x.detail,
                          "created_at": stamp(x.created_at), "actor_name": db.get(User, x.actor_id).name if x.actor_id else "System"}
                         for x in events if user.role != "employee" or x.event_type not in {"AI_FAILED", "REVIEW_REQUIRED"}]
    result["ai_run"] = ({"category": run.category, "priority": run.priority, "summary": run.summary,
                          "reason": run.reason, "confidence": run.confidence, "provider": run.provider,
                          "model": run.model, "status": run.status} if run and user.role != "employee" else None)
    return result


@app.post("/api/tickets/{ticket_id}/comments", status_code=201)
def add_comment(ticket_id: int, body: CommentInput, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    if ticket.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed tickets cannot be commented on")
    if user.role == "employee" and body.is_internal:
        raise HTTPException(status_code=403, detail="Internal notes are for agents")
    comment = Comment(ticket_id=ticket.id, author_id=user.id, body=body.body.strip(), is_internal=body.is_internal)
    db.add(comment)
    if user.role in {"agent", "admin"} and not body.is_internal and not ticket.first_response_at:
        ticket.first_response_at = datetime.now(timezone.utc)
    if user.role == "employee" and ticket.status == "WAITING_FOR_EMPLOYEE":
        extend_waiting_sla(db, ticket, datetime.now(timezone.utc))
        ticket.status = "IN_PROGRESS"
        event(db, ticket.id, "STATUS_CHANGED", "WAITING_FOR_EMPLOYEE → IN_PROGRESS after requester reply", user.id)
    event(db, ticket.id, "INTERNAL_NOTE" if body.is_internal else "COMMENT", f"{user.name} added a {'note' if body.is_internal else 'reply'}", user.id)
    db.commit()
    return {"id": comment.id, "ok": True}


@app.patch("/api/tickets/{ticket_id}/status")
def change_status(ticket_id: int, body: StatusInput, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    target = body.status.upper()
    if target not in STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status")
    if user.role == "employee":
        if not (ticket.status == "RESOLVED" and target == "OPEN"):
            raise HTTPException(status_code=403, detail="Employees can only reopen resolved tickets")
    else:
        allowed = {
            "NEW": {"TRIAGING", "OPEN"}, "TRIAGING": {"OPEN", "IN_PROGRESS"},
            "OPEN": {"IN_PROGRESS", "WAITING_FOR_EMPLOYEE", "RESOLVED"},
            "IN_PROGRESS": {"WAITING_FOR_EMPLOYEE", "RESOLVED", "OPEN"},
            "WAITING_FOR_EMPLOYEE": {"IN_PROGRESS", "RESOLVED"},
            "ESCALATED": {"IN_PROGRESS", "WAITING_FOR_EMPLOYEE", "RESOLVED"},
            "RESOLVED": {"CLOSED", "OPEN"}, "CLOSED": set(),
        }
        if target not in allowed[ticket.status]:
            raise HTTPException(status_code=409, detail="Status transition is not allowed")
    old = ticket.status
    now = datetime.now(timezone.utc)
    if old == "WAITING_FOR_EMPLOYEE" and target != old:
        extend_waiting_sla(db, ticket, now)
    if target == "WAITING_FOR_EMPLOYEE":
        ticket.waiting_started_at = now
    if target == "RESOLVED":
        ticket.resolved_at = now
    if old == "RESOLVED" and target == "OPEN":
        ticket.resolved_at = None
        ticket.resolution_breached_at = None
        policy = db.scalar(select(SLAPolicy).where(SLAPolicy.priority == ticket.final_priority))
        if policy:
            ticket.resolution_due_at = deadline(now, policy.resolution_minutes, policy.calendar_mode)
    if target in {"OPEN", "IN_PROGRESS"}:
        ticket.triage_review_required = False
    ticket.status = target
    event(db, ticket.id, "STATUS_CHANGED", f"{old} → {target}", user.id)
    db.commit()
    return ticket_data(db, ticket)


@app.patch("/api/tickets/{ticket_id}/assignment")
def assign(ticket_id: int, body: AssignmentInput, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    team = db.get(Team, body.team_id)
    if not team:
        raise HTTPException(status_code=422, detail="Unknown team")
    agent = db.get(User, body.agent_id) if body.agent_id else None
    if body.agent_id and (not agent or agent.team_id != team.id or agent.role != "agent"):
        raise HTTPException(status_code=422, detail="Agent must belong to selected team")
    ticket.assigned_team_id = team.id
    ticket.assigned_agent_id = agent.id if agent else None
    event(db, ticket.id, "ASSIGNED", f"Assigned to {team.name}" + (f" / {agent.name}" if agent else ""), user.id)
    db.commit()
    return ticket_data(db, ticket)


@app.patch("/api/tickets/{ticket_id}/priority")
def set_priority(ticket_id: int, body: PriorityInput, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    priority = body.priority.upper()
    if priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail="Unknown priority")
    old = ticket.final_priority
    ticket.final_priority = priority
    apply_sla(db, ticket)
    event(db, ticket.id, "PRIORITY_CHANGED", f"{old or 'none'} → {priority}", user.id)
    db.commit()
    return ticket_data(db, ticket)


@app.patch("/api/tickets/{ticket_id}/category")
def set_category(ticket_id: int, body: CategoryInput, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    ticket = accessible_ticket(db, ticket_id, user)
    category = body.category.upper()
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category")
    old = ticket.category
    ticket.category = category
    team = db.scalar(select(Team).where(Team.category == category))
    ticket.assigned_team_id = team.id if team else None
    ticket.assigned_agent_id = None
    event(db, ticket.id, "CATEGORY_CHANGED", f"{old} → {category}; routed to {team.name if team else 'manual triage'}", user.id)
    db.commit()
    return ticket_data(db, ticket)


@app.get("/api/admin/sla-policies")
def list_policies(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    return [{"id": x.id, "priority": x.priority, "response_minutes": x.response_minutes,
             "resolution_minutes": x.resolution_minutes, "calendar_mode": x.calendar_mode}
            for x in db.scalars(select(SLAPolicy).order_by(SLAPolicy.priority))]


@app.patch("/api/admin/sla-policies/{policy_id}")
def edit_policy(policy_id: int, body: PolicyInput, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    policy = db.get(SLAPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.response_minutes = body.response_minutes
    policy.resolution_minutes = body.resolution_minutes
    policy.calendar_mode = body.calendar_mode
    db.commit()
    return {"ok": True}


@app.patch("/api/admin/teams/{team_id}")
def edit_team(team_id: int, body: TeamInput, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if body.lead_user_id:
        lead = db.get(User, body.lead_user_id)
        if not lead or lead.role not in {"agent", "admin"}:
            raise HTTPException(status_code=422, detail="Lead must be an agent or admin")
    team.name = body.name.strip()
    team.lead_user_id = body.lead_user_id
    db.commit()
    return {"id": team.id, "name": team.name}


@app.get("/api/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    items = db.scalars(select(Notification).where(Notification.recipient_id == user.id).order_by(desc(Notification.created_at)).limit(30)).all()
    return [{"id": x.id, "ticket_id": x.ticket_id, "message": x.message,
             "created_at": stamp(x.created_at), "read_at": stamp(x.read_at)} for x in items]


@app.post("/api/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    item = db.get(Notification, notification_id)
    if not item or item.recipient_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    item.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.get("/api/dashboard/metrics")
def metrics(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    query = select(Ticket)
    if user.role == "employee":
        query = query.where(Ticket.requester_id == user.id)
    elif user.role == "agent":
        query = query.where((Ticket.assigned_team_id == user.team_id) | (Ticket.assigned_team_id.is_(None)))
    tickets = db.scalars(query).all()
    categories = Counter(x.category for x in tickets)
    active = [x for x in tickets if x.status not in {"RESOLVED", "CLOSED"}]
    return {"total": len(tickets), "active": len(active),
            "resolved": len(tickets)-len(active),
            "breached": sum(bool(x.response_breached_at or x.resolution_breached_at) for x in tickets),
            "needs_review": sum(x.triage_review_required for x in active),
            "categories": dict(categories),
            "recent": [ticket_data(db, x) for x in sorted(tickets, key=lambda t: t.created_at, reverse=True)[:5]]}


@app.post("/api/admin/run-sla-check")
def run_sla_check(_: User = Depends(require_admin)) -> dict:
    return {"escalated": check_sla_now()}

