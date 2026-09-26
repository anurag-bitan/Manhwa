"""Firebase ID token verification for protected FastAPI routes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationConfigurationError(RuntimeError):
    """Raised when Firebase authentication settings are absent."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity derived only from a verified Firebase ID token."""

    sub: str
    username: str | None
    groups: tuple[str, ...]
    claims: dict[str, Any]


def _initialize_firebase() -> None:
    if firebase_admin._apps:
        return
    project_id = settings.firebase_project_id.strip()
    if not project_id:
        raise AuthenticationConfigurationError(
            "FIREBASE_PROJECT_ID must be configured."
        )
    cred: Any
    sa_path = settings.firebase_service_account_path.strip()
    sa_json = settings.firebase_service_account_json.strip()
    if sa_path:
        cred = credentials.Certificate(sa_path)
    elif sa_json:
        cred = credentials.Certificate(json.loads(sa_json))
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, options={"projectId": project_id})


@lru_cache(maxsize=1)
def _firebase_ready() -> bool:
    _initialize_firebase()
    return True


def verify_firebase_token(token: str) -> dict[str, Any]:
    if not token or len(token) > 16_384:
        raise ValueError("Malformed ID token")
    _firebase_ready()
    claims = firebase_auth.verify_id_token(token, check_revoked=False)
    subject = claims.get("uid") or claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise ValueError("ID token has no subject")
    return claims


def _unauthorized(detail: str = "Invalid or expired access token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise _unauthorized("Authentication required")

    try:
        claims = await run_in_threadpool(verify_firebase_token, credentials.credentials)
    except AuthenticationConfigurationError:
        logger.exception("Firebase authentication is not configured correctly")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured",
        )
    except Exception:
        raise _unauthorized()

    subject = str(claims.get("uid") or claims.get("sub") or "")
    email = claims.get("email")
    name = claims.get("name")

    return AuthenticatedUser(
        sub=subject,
        username=email if isinstance(email, str) else (
            name if isinstance(name, str) else None
        ),
        groups=(),
        claims=claims,
    )
