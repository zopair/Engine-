from __future__ import annotations

import hmac
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from core.config import settings


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if not settings.api_key:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


APIKeyDependency = Depends(verify_api_key)
