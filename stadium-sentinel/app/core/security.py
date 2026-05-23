from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status

from app.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_pw(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_pw(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def mint_token(sub: str, role: str) -> str:
    """Returns a signed JWT. sub is the user id, role gates WebSocket topics."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_TTL_MIN)
    return jwt.encode(
        {"sub": sub, "role": role, "exp": exp},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALG,
    )


def decode_token(token: str) -> dict:
    """Returns payload or raises 401."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG],
        )
    except JWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        )
