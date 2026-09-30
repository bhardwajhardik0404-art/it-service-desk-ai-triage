import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${value.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, expected = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(candidate, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def make_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    password_version = hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]
    return jwt.encode({"sub": str(user.id), "pwd": password_version, "exp": expires},
                      get_settings().secret_key, algorithm="HS256")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("desk_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        user = None
    if not user or payload.get("pwd") != hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role not in {"agent", "admin"}:
        raise HTTPException(status_code=403, detail="Agent access required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

