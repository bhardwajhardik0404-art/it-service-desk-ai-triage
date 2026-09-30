from datetime import datetime, timezone

from app.sla import add_business_minutes, business_minutes_between, deadline


def test_business_time_skips_weekend():
    # Friday 16:30 in Asia/Kolkata, then eight business hours.
    friday = datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)
    due = add_business_minutes(friday, 480, 'Asia/Kolkata')
    assert due == datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)


def test_business_time_between_and_always_mode():
    start = datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)
    assert business_minutes_between(start, end, 'Asia/Kolkata') == 480
    assert deadline(start, 60, 'always') == datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

