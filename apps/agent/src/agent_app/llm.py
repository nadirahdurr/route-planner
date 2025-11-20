from __future__ import annotations

from functools import lru_cache

from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

from agent_app.config import get_settings


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached ChatOllama instance configured from settings."""

    settings = get_settings()
    return ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model)
