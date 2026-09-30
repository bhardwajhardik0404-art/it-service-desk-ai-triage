"""Create schema and a repeatable portfolio demo dataset."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .auth import hash_password
from .database import Base, SessionLocal, engine
from .models import AITriageRun, Comment, SLAPolicy, Team, Ticket, TicketEvent, User
from .sla import apply_sla


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            return
        teams = [
            Team(name="Device Support", category="HARDWARE"),
            Team(name="Applications", category="SOFTWARE"),
            Team(name="Identity & Access", category="ACCESS"),
            Team(name="General IT", category="OTHER"),
        ]
        db.add_all(teams)
        db.flush()
        users = [
            User(name="Aarav Mehta", email="employee@demo.dev", password_hash=hash_password("Demo123!"), role="employee"),
            User(name="Priya Nair", email="agent@demo.dev", password_hash=hash_password("Demo123!"), role="agent", team_id=teams[2].id),
            User(name="Samir Shah", email="admin@demo.dev", password_hash=hash_password("Demo123!"), role="admin"),
            User(name="Riya Das", email="device.agent@demo.dev", password_hash=hash_password("Demo123!"), role="agent", team_id=teams[0].id),
            User(name="Leo Thomas", email="apps.agent@demo.dev", password_hash=hash_password("Demo123!"), role="agent", team_id=teams[1].id),
        ]
        db.add_all(users)
        db.flush()
        teams[2].lead_user_id = users[1].id
        teams[0].lead_user_id = users[3].id
        teams[1].lead_user_id = users[4].id
        policies = [
            SLAPolicy(priority="P1", response_minutes=15, resolution_minutes=240, calendar_mode="always"),
            SLAPolicy(priority="P2", response_minutes=60, resolution_minutes=480, calendar_mode="business"),
            SLAPolicy(priority="P3", response_minutes=240, resolution_minutes=960, calendar_mode="business"),
            SLAPolicy(priority="P4", response_minutes=480, resolution_minutes=2400, calendar_mode="business"),
        ]
        db.add_all(policies)
        db.flush()
        now = datetime.now(timezone.utc)
        samples = [
            ("Payroll login blocked after password reset", "The payroll page says my account is locked after I changed my password. I need access before today's deadline.", "Payroll", "individual", "high", "ACCESS", "P2", "IN_PROGRESS", teams[2].id, users[1].id, 2),
            ("Laptop screen flickers during meetings", "The screen flickers several times each hour and makes video calls difficult.", "Laptop", "individual", "normal", "HARDWARE", "P3", "OPEN", teams[0].id, users[3].id, 4),
            ("Design application crashes on launch", "Our team cannot open the design application after this morning's update.", "Design app", "team", "high", "SOFTWARE", "P2", "OPEN", teams[1].id, users[4].id, 1),
            ("Request a second monitor", "I would like a second monitor for my desk when equipment is available.", "Equipment", "individual", "low", "HARDWARE", "P4", "RESOLVED", teams[0].id, users[3].id, 8),
        ]
        for title, description, service, impact, urgency, category, priority, status, team_id, agent_id, hours_old in samples:
            ticket = Ticket(requester_id=users[0].id, title=title, description=description,
                            affected_service=service, impact=impact, urgency=urgency,
                            category=category, ai_suggested_priority=priority, final_priority=priority,
                            status=status, assigned_team_id=team_id, assigned_agent_id=agent_id,
                            created_at=now-timedelta(hours=hours_old), updated_at=now-timedelta(hours=hours_old))
            db.add(ticket)
            db.flush()
            ticket.number = f"INC-{ticket.id:05d}"
            apply_sla(db, ticket)
            if status == "RESOLVED":
                ticket.first_response_at = now-timedelta(hours=5)
                ticket.resolved_at = now-timedelta(hours=3)
            if status == "IN_PROGRESS":
                ticket.first_response_at = now-timedelta(hours=1)
            db.add(AITriageRun(ticket_id=ticket.id, provider="demo", model="keyword-rules-v1",
                               category=category, priority=priority, summary=title,
                               reason="Seeded demo classification for the portfolio walkthrough.",
                               confidence=0.88, status="completed"))
            db.add(TicketEvent(ticket_id=ticket.id, actor_id=users[0].id, event_type="CREATED", detail="Ticket submitted"))
            db.add(TicketEvent(ticket_id=ticket.id, event_type="AI_TRIAGE", detail=f"Suggested {category} / {priority}"))
            db.add(TicketEvent(ticket_id=ticket.id, event_type="ASSIGNED", detail=f"Assigned to {next(t.name for t in teams if t.id == team_id)}"))
            if status == "IN_PROGRESS":
                db.add(Comment(ticket_id=ticket.id, author_id=users[1].id, body="I am checking your account permissions now.", is_internal=False))
        overdue = Ticket(requester_id=users[0].id, title="VPN unavailable for sales team",
                         description="Several colleagues cannot connect to VPN, blocking access to shared sales files.",
                         affected_service="VPN", impact="team", urgency="high", category="SOFTWARE",
                         ai_suggested_priority="P2", final_priority="P2", status="OPEN",
                         assigned_team_id=teams[1].id, created_at=now-timedelta(days=4),
                         updated_at=now-timedelta(days=4), response_due_at=now-timedelta(hours=2),
                         resolution_due_at=now+timedelta(hours=2))
        db.add(overdue)
        db.flush()
        overdue.number = f"INC-{overdue.id:05d}"
        db.add(TicketEvent(ticket_id=overdue.id, actor_id=users[0].id, event_type="CREATED", detail="Ticket submitted"))
        db.add(AITriageRun(ticket_id=overdue.id, provider="demo", model="keyword-rules-v1",
                           category="SOFTWARE", priority="P2", summary=overdue.title,
                           reason="Team access blocked.", confidence=0.87, status="completed"))
        db.commit()


if __name__ == "__main__":
    seed()
    print("Demo data ready: employee@demo.dev, agent@demo.dev, admin@demo.dev / Demo123!")

