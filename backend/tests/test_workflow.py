from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.jobs import check_sla_now
from app.models import Notification, Ticket


def create_ticket(client, title='Cannot access payroll application', urgency='high'):
    response = client.post('/api/tickets', json={
        'title': title, 'description': 'My account is locked and I cannot log in to payroll.',
        'affected_service': 'Payroll', 'impact': 'individual', 'urgency': urgency,
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_ai_triage_routes_and_explains(clients):
    ticket_id = create_ticket(clients['employee'])
    detail = clients['agent'].get(f'/api/tickets/{ticket_id}').json()
    assert detail['category'] == 'ACCESS'
    assert detail['final_priority'] == 'P2'
    assert detail['assigned_team_name'] == 'Identity'
    assert detail['status'] == 'OPEN'
    assert detail['response_due_at']
    assert detail['ai_run']['provider'] == 'demo'
    assert detail['ai_run']['confidence'] >= 0.65


def test_critical_suggestion_requires_review(clients):
    response = clients['employee'].post('/api/tickets', json={
        'title': 'Company-wide payroll access outage',
        'description': 'Nobody in the company can open payroll and a deadline is approaching.',
        'affected_service': 'Payroll', 'impact': 'company', 'urgency': 'critical',
    })
    assert response.status_code == 201
    detail = clients['admin'].get(f"/api/tickets/{response.json()['id']}").json()
    assert detail['ai_suggested_priority'] == 'P1'
    assert detail['status'] == 'TRIAGING'
    assert detail['triage_review_required'] is True


def test_roles_and_internal_notes(clients):
    ticket_id = create_ticket(clients['employee'])
    assert clients['other'].get(f'/api/tickets/{ticket_id}').status_code == 404
    assert clients['employee'].patch(f'/api/tickets/{ticket_id}/priority', json={'priority': 'P1'}).status_code == 403
    assert clients['employee'].post(f'/api/tickets/{ticket_id}/comments', json={'body': 'secret', 'is_internal': True}).status_code == 403
    response = clients['agent'].post(f'/api/tickets/{ticket_id}/comments', json={'body': 'Checking access policy.', 'is_internal': True})
    assert response.status_code == 201
    assert clients['employee'].get(f'/api/tickets/{ticket_id}').json()['comments'] == []
    response = clients['agent'].post(f'/api/tickets/{ticket_id}/comments', json={'body': 'We are investigating.', 'is_internal': False})
    assert response.status_code == 201
    detail = clients['employee'].get(f'/api/tickets/{ticket_id}').json()
    assert len(detail['comments']) == 1
    assert detail['first_response_at'] is not None
    assert clients['agent'].get('/api/admin/sla-policies').status_code == 403


def test_status_transitions_and_reopen(clients):
    ticket_id = create_ticket(clients['employee'])
    assert clients['employee'].patch(f'/api/tickets/{ticket_id}/status', json={'status': 'RESOLVED'}).status_code == 403
    assert clients['agent'].patch(f'/api/tickets/{ticket_id}/status', json={'status': 'RESOLVED'}).status_code == 200
    reopened = clients['employee'].patch(f'/api/tickets/{ticket_id}/status', json={'status': 'OPEN'})
    assert reopened.status_code == 200
    assert reopened.json()['resolution_due_at'] is not None
    assert clients['agent'].patch(f'/api/tickets/{ticket_id}/status', json={'status': 'CLOSED'}).status_code == 409


def test_employee_reply_resumes_waiting_ticket(clients, setup_db):
    ticket_id = create_ticket(clients['employee'])
    waiting = clients['agent'].patch(f'/api/tickets/{ticket_id}/status', json={'status': 'WAITING_FOR_EMPLOYEE'})
    assert waiting.status_code == 200
    with setup_db() as db:
        ticket = db.get(Ticket, ticket_id)
        before = ticket.resolution_due_at
        ticket.waiting_started_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
    reply = clients['employee'].post(f'/api/tickets/{ticket_id}/comments', json={'body': 'I tried again and can share the error screenshot text.'})
    assert reply.status_code == 201
    with setup_db() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket.status == 'IN_PROGRESS'
        assert ticket.waiting_started_at is None
        assert ticket.resolution_due_at >= before


def test_sla_escalation_is_idempotent(clients, setup_db):
    ticket_id = create_ticket(clients['employee'])
    with setup_db() as db:
        ticket = db.get(Ticket, ticket_id)
        ticket.response_due_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
        before = len(db.scalars(select(Notification).where(Notification.ticket_id == ticket_id)).all())
    assert check_sla_now() == 1
    assert check_sla_now() == 0
    with setup_db() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket.status == 'ESCALATED'
        assert ticket.response_breached_at is not None
        assert len(db.scalars(select(Notification).where(Notification.ticket_id == ticket_id)).all()) == before + 1

