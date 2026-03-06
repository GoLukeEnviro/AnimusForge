"""API Routes module."""
from fastapi import APIRouter

from .persona import router as persona_router
from .llm import router as llm_router
from .killswitch import router as killswitch_router
from .memory import router as memory_router
from .ethics import router as ethics_router
from .system import router as system_router


__all__ = [
    "persona_router",
    "llm_router",
    "killswitch_router",
    "memory_router",
    "ethics_router",
    "system_router",
]
