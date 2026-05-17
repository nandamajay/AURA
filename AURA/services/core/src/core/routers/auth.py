"""Authentication endpoints — JWT-based login/logout."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.governance import Role
from core.config import Config

logger = get_logger("core.auth")
router = APIRouter()
security = HTTPBearer(auto_error=False)

class LoginRequest(BaseModel):
    """Login request payload."""

    email: str = ""
    password: str = ""


# JWT utilities
try:
    from jose import jwt, JWTError
    import bcrypt
    HAS_AUTH = True
except ImportError:
    HAS_AUTH = False
    jwt = None
    bcrypt = None


def _create_token(user_id: str, email: str, role: str) -> str:
    """Create a JWT access token."""
    if not jwt:
        raise HTTPException(status_code=500, detail="JWT library not available")
    expire = datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXPIRY_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def _verify_token(token: str) -> dict:
    """Verify a JWT token. Returns payload or raises."""
    if not jwt:
        raise HTTPException(status_code=500, detail="JWT library not available")
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI dependency to get current authenticated user."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _verify_token(credentials.credentials)


@router.post("/login")
async def login(body: LoginRequest):
    """Login with email/password. Returns JWT token."""
    email = body.email.lower().strip()
    password = body.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    if not HAS_AUTH:
        raise HTTPException(status_code=500, detail="Auth dependencies not installed")

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, email, password_hash, role, display_name FROM users WHERE email = ? AND is_active = 1",
            (email,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user = dict(row)
        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Update last login
        await db.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (int(datetime.now(timezone.utc).timestamp()), user["id"]),
        )
        await db.commit()

        token = _create_token(user["id"], user["email"], user["role"])

        logger.info("user_login", email=email, role=user["role"])

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
                "display_name": user["display_name"],
            },
        }


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout — client discards token. Server logs the event."""
    logger.info("user_logout", user_id=current_user.get("sub"))
    return {"message": "Logged out"}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": current_user.get("sub"),
        "email": current_user.get("email"),
        "role": current_user.get("role"),
    }
