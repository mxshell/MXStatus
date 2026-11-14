import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    token = os.environ.get("MXSTATUS_ADMIN_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(
            status_code=503,
            detail="Set MXSTATUS_ADMIN_TOKEN to a random token of at least 32 characters, then restart the server.",
        )
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), token.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
