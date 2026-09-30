from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import AITriageRun, Notification, Team, Ticket, TicketEvent, User
from .sla import apply_sla, aware_utc
from .triage import classify


settings = get_settings()
celery_app = Celery("service_desk", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {"check-sla-every-minute": {"task": "app.jobs.check_sla", "schedule": 60.0}}
celery_app.conf.timezone = "UTC"


def event(db, ticket_id: int, kind: str, detail: str, actor_id: int | None = None) -> None:
    db.add(TicketEvent(ticket_id=ticket_id, actor_id=actor_id, event_type=kind, detail=detail))


def notify_team(db, ticket: Ticket, message: str) -> None:
    if ticket.assigned_team_id is None:
        return
    team = db.get(Team, ticket.assigned_team_id)
    recipients = db.scalars(select(User).where(User.team_id == team.id, User.role == "agent")).all()
    if team.lead_user_id:
        lead = db.get(User, team.lead_user_id)
        if lead and all(item.id != lead.id for item in recipients):
            recipients.append(lead)
    for recipient in recipients:
        db.add(Notification(recipient_id=recipient.id, ticket_id=ticket.id, message=message))


def triage_ticket_now(ticket_id: int) -> None:
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket or ticket.status not in {"NEW", "TRIAGING"}:
            return
        ticket.status = "TRIAGING"
        db.commit()
        try:
            result, provider, model = classify(ticket)
            team = db.scalar(select(Team).where(Team.category == result.category))
            ticket.category = result.category
            ticket.ai_suggested_priority = result.priority
            ticket.final_priority = result.priority
            ticket.assigned_team_id = team.id if team else None
            ticket.triage_review_required = result.priority == "P1" or result.confidence < 0.65 or result.category == "OTHER"
            ticket.status = "TRIAGING" if ticket.triage_review_required else "OPEN"
            apply_sla(db, ticket)
            db.add(AITriageRun(ticket_id=ticket.id, provider=provider, model=model,
                               category=result.category, priority=result.priority,
                               summary=result.summary, reason=result.reason,
                               confidence=result.confidence, status="completed"))
            event(db, ticket.id, "AI_TRIAGE", f"{provider} suggested {result.category} / {result.priority}; confidence {result.confidence:.2f}")
            event(db, ticket.id, "ASSIGNED", f"Routed to {team.name if team else 'manual triage'}")
            if ticket.triage_review_required:
                event(db, ticket.id, "REVIEW_REQUIRED", "Agent review required before work begins")
            notify_team(db, ticket, f"{ticket.number} is ready for your team")
            db.commit()
        except Exception as exc:
            db.rollback()
            ticket = db.get(Ticket, ticket_id)
            ticket.status = "TRIAGING"
            ticket.triage_review_required = True
            db.add(AITriageRun(ticket_id=ticket.id, provider=settings.ai_provider, model=settings.openai_model,
                               status="failed", reason=str(exc)[:400]))
            event(db, ticket.id, "AI_FAILED", "AI triage failed; manual review required")
            db.commit()


@celery_app.task(name="app.jobs.triage_ticket")
def triage_ticket(ticket_id: int) -> None:
    triage_ticket_now(ticket_id)


def check_sla_now(now: datetime | None = None) -> int:
    now = aware_utc(now or datetime.now(timezone.utc))
    count = 0
    with SessionLocal() as db:
        tickets = db.scalars(select(Ticket).where(Ticket.status.not_in(["RESOLVED", "CLOSED"]))).all()
        for ticket in tickets:
            breached = []
            if ticket.response_due_at and not ticket.first_response_at and not ticket.response_breached_at and aware_utc(ticket.response_due_at) <= now:
                ticket.response_breached_at = now
                breached.append("first response")
            if ticket.resolution_due_at and not ticket.resolved_at and not ticket.resolution_breached_at and ticket.status != "WAITING_FOR_EMPLOYEE" and aware_utc(ticket.resolution_due_at) <= now:
                ticket.resolution_breached_at = now
                breached.append("resolution")
            if breached:
                ticket.status = "ESCALATED"
                message = f"{ticket.number} breached {' and '.join(breached)} SLA"
                event(db, ticket.id, "SLA_BREACH", message)
                notify_team(db, ticket, message)
                count += 1
        db.commit()
    return count


@celery_app.task(name="app.jobs.check_sla")
def check_sla() -> int:
    return check_sla_now()

