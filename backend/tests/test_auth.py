from fastapi.testclient import TestClient

from app.main import app


def test_employee_registration_and_login(setup_db):
    client = TestClient(app)
    account = {"name": "  New Employee  ", "email": "  NEW@EXAMPLE.COM  ", "password": "AUniquePassword123", "role": "admin"}
    response = client.post("/api/auth/register", json=account)
    assert response.status_code == 201
    assert response.json()["role"] == "employee"
    assert response.json()["name"] == "New Employee"
    assert response.json()["email"] == "new@example.com"
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/register", json=account).status_code == 409
    assert client.post("/api/auth/register", json={**account, "email": "short@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={**account, "name": "   ", "email": "blank@example.com"}).status_code == 422
    assert client.post("/api/auth/register", json={**account, "email": "letters@example.com", "password": "onlyletters"}).status_code == 422

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "missing@example.com", "password": account["password"]}).json()["detail"] == "Invalid email or password"
    assert client.post("/api/auth/login", json={"email": account["email"], "password": "wrong"}).json()["detail"] == "Invalid email or password"
    assert client.post("/api/auth/login", json={"email": account["email"], "password": account["password"]}).status_code == 200


def test_only_admin_can_create_agent(clients):
    account = {"name": "New Agent", "email": "agent.new@example.com", "password": "AnotherPassword123", "team_id": 1}
    assert clients["employee"].post("/api/admin/agents", json=account).status_code == 403
    assert clients["agent"].post("/api/admin/agents", json=account).status_code == 403
    response = clients["admin"].post("/api/admin/agents", json=account)
    assert response.status_code == 201
    assert response.json()["role"] == "agent"
    assert response.json()["team_id"] == 1
    assert clients["admin"].post("/api/admin/agents", json=account).status_code == 409
    new_agent = TestClient(app)
    assert new_agent.post("/api/auth/login", json={"email": account["email"], "password": account["password"]}).status_code == 200


def test_password_change_invalidates_old_session(clients):
    client = clients["employee"]
    old_cookie = client.cookies.get("desk_session")
    assert client.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "NewPassword123"}).status_code == 400
    assert client.post("/api/auth/change-password", json={"current_password": "Password123!", "new_password": "onlyletters"}).status_code == 422
    response = client.post("/api/auth/change-password", json={"current_password": "Password123!", "new_password": "NewPassword123"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    old_session = TestClient(app)
    old_session.cookies.set("desk_session", old_cookie)
    assert old_session.get("/api/auth/me").status_code == 401
    assert old_session.post("/api/auth/login", json={"email": "employee@test.dev", "password": "Password123!"}).status_code == 401
    assert old_session.post("/api/auth/login", json={"email": "employee@test.dev", "password": "NewPassword123"}).status_code == 200
