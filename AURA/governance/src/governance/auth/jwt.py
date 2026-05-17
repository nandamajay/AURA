"""JWT token creation and verification."""

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from jose import jwt, JWTError
    HAS_JWT = True
except ImportError:
    HAS_JWT = False


def create_token(
    user_id: str,
    email: str,
    role: str,
    secret: str,
    expiry_hours: int = 24,
) -> str:
    """Create a JWT access token."""
    if not HAS_JWT:
        raise RuntimeError("jose library not installed")
    expire = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict[str, Any]:
    """Verify a JWT token. Returns payload."""
    if not HAS_JWT:
        raise RuntimeError("jose library not installed")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
