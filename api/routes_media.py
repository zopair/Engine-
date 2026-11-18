from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible"])
