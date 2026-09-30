import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import jobs
from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import SLAPolicy, Team, User


@pytest.fixture
def setup_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", Session)
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    with Session() as db:
        access = Team(name="Identity", category="ACCESS")
        other = Team(name="General IT", category="OTHER")
        db.add_all([access, other]); db.flush()
        db.add_all([
            User(name="Employee One", email="employee@test.dev", password_hash=hash_password("Password123!"), role="employee"),
            User(name="Employee Two", email="other@test.dev", password_hash=hash_password("Password123!"), role="employee"),
            User(name="Agent One", email="agent@test.dev", password_hash=hash_password("Password123!"), role="agent", team_id=access.id),
            User(name="Admin One", email="admin@test.dev", password_hash=hash_password("Password123!"), role="admin"),
        ])
        db.add_all([
            SLAPolicy(priority="P1", response_minutes=15, resolution_minutes=240, calendar_mode="always"),
            SLAPolicy(priority="P2", response_minutes=60, resolution_minutes=480, calendar_mode="business"),
            SLAPolicy(priority="P3", response_minutes=240, resolution_minutes=960, calendar_mode="business"),
            SLAPolicy(priority="P4", response_minutes=480, resolution_minutes=2400, calendar_mode="business"),
        ])
        db.commit()
    yield Session
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def clients(setup_db):
    result = {}
    for role, email in [('employee','employee@test.dev'), ('other','other@test.dev'), ('agent','agent@test.dev'), ('admin','admin@test.dev')]:
        client = TestClient(app)
        response = client.post('/api/auth/login', json={'email': email, 'password': 'Password123!'})
        assert response.status_code == 200
        result[role] = client
    return result

