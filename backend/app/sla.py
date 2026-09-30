from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import SLAPolicy, Ticket


WORK_START = time(9, 0)
WORK_END = time(17, 0)


def aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def add_business_minutes(start: datetime, minutes: int, timezone_name: str) -> datetime:
    """Add working minutes, Monday-Friday 09:00-17:00 in the support timezone."""
    if minutes < 0:
        raise ValueError("minutes must be non-negative")
    zone = ZoneInfo(timezone_name)
    current = aware_utc(start).astimezone(zone)
    remaining = minutes
    while True:
        day_open = datetime.combine(current.date(), WORK_START, zone)
        day_close = datetime.combine(current.date(), WORK_END, zone)
        if current.weekday() >= 5 or current >= day_close:
            current = datetime.combine(current.date() + timedelta(days=1), WORK_START, zone)
            continue
        if current < day_open:
            current = day_open
        available = int((day_close - current).total_seconds() // 60)
        if remaining <= available:
            return (current + timedelta(minutes=remaining)).astimezone(timezone.utc)
        remaining -= available
        current = datetime.combine(current.date() + timedelta(days=1), WORK_START, zone)


def deadline(start: datetime, minutes: int, mode: str) -> datetime:
    if mode == "always":
        return aware_utc(start) + timedelta(minutes=minutes)
    return add_business_minutes(start, minutes, get_settings().sla_timezone)


def business_minutes_between(start: datetime, end: datetime, timezone_name: str) -> int:
    if aware_utc(end) <= aware_utc(start):
        return 0
    zone = ZoneInfo(timezone_name)
    current = aware_utc(start).astimezone(zone)
    finish = aware_utc(end).astimezone(zone)
    total = 0
    while current.date() <= finish.date():
        if current.weekday() < 5:
            left = max(current, datetime.combine(current.date(), WORK_START, zone))
            right = min(finish, datetime.combine(current.date(), WORK_END, zone))
            if right > left:
                total += int((right-left).total_seconds() // 60)
        current = datetime.combine(current.date() + timedelta(days=1), time.min, zone)
    return total


def apply_sla(db: Session, ticket: Ticket) -> None:
    if not ticket.final_priority:
        return
    policy = db.scalar(select(SLAPolicy).where(SLAPolicy.priority == ticket.final_priority))
    if not policy:
        return
    ticket.response_due_at = deadline(ticket.created_at, policy.response_minutes, policy.calendar_mode)
    ticket.resolution_due_at = deadline(ticket.created_at, policy.resolution_minutes, policy.calendar_mode)


def extend_waiting_sla(db: Session, ticket: Ticket, resumed_at: datetime) -> None:
    if not ticket.waiting_started_at or not ticket.resolution_due_at or not ticket.final_priority:
        ticket.waiting_started_at = None
        return
    policy = db.scalar(select(SLAPolicy).where(SLAPolicy.priority == ticket.final_priority))
    if policy:
        if policy.calendar_mode == "always":
            paused = int((aware_utc(resumed_at) - aware_utc(ticket.waiting_started_at)).total_seconds() // 60)
        else:
            paused = business_minutes_between(ticket.waiting_started_at, resumed_at, get_settings().sla_timezone)
        ticket.resolution_due_at = deadline(ticket.resolution_due_at, max(0, paused), policy.calendar_mode)
    ticket.waiting_started_at = None

