
import os
from typing import Any
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

def get_llm(model_type: str = "default") -> BaseChatModel:
    """
    Returns an LLM instance with fallback capability.
    Priority:
    1. Local (LM Studio/Ollama) - if LLM_PRIORITY is 'local'
    2. Anthropic (if key available and not rate-limited)
    3. OpenRouter (DeepSeek-V3 or similar)
    """
    
    priority = os.getenv("LLM_PRIORITY", "openrouter").lower()
    
    # 1. Local Development Mode (LM Studio / Ollama)
    if priority == "local":
        local_base = os.getenv("LOCAL_LLM_BASE", "http://localhost:1234/v1")
        log.info("initializing_llm", provider="local", base_url=local_base)
        return ChatOpenAI(
            model=os.getenv("LOCAL_LLM_MODEL", "local-model"),
            openai_api_key="not-needed",
            openai_api_base=local_base,
            temperature=0
        )

    # 2. Try Anthropic if priority is set
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if priority == "anthropic" and anthropic_key:
        try:
            log.info("initializing_llm", provider="anthropic")
            return ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                anthropic_api_key=anthropic_key,
                temperature=0
            )
        except Exception as e:
            log.warning("anthropic_init_failed_falling_back", error=str(e))

    # 3. OpenRouter (Primary for production if priority is 'openrouter')
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        log.info("initializing_llm", provider="openrouter", model="deepseek-v3")
        return ChatOpenAI(
            model="deepseek/deepseek-chat",
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0,
            default_headers={
                "HTTP-Referer": "https://mazao-ai.fly.dev",
                "X-Title": "Mazao AI"
            }
        )
    
    # 4. Final Fallback to Anthropic (if available)
    if anthropic_key:
        log.info("initializing_llm", provider="anthropic", mode="last_resort")
        return ChatAnthropic(
            model="claude-3-5-sonnet-20240620",
            anthropic_api_key=anthropic_key,
            temperature=0
        )

    raise ValueError("No LLM provider configured. Please set ANTHROPIC_API_KEY or OPENROUTER_API_KEY.")
