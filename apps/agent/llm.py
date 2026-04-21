
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
    1. Anthropic (if key available and not rate-limited)
    2. OpenRouter (DeepSeek-V3 or similar)
    """
    
    # 1. Try Anthropic if configured and priority is set
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    use_anthropic = os.getenv("LLM_PRIORITY", "openrouter").lower() == "anthropic"
    
    if use_anthropic and anthropic_key:
        try:
            log.info("initializing_llm", provider="anthropic")
            return ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                anthropic_api_key=anthropic_key,
                temperature=0
            )
        except Exception as e:
            log.warning("anthropic_init_failed_falling_back", error=str(e))

    # 2. Fallback to OpenRouter (DeepSeek-V3 is excellent for financial logic)
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
    
    # 3. Last resort: Anthropic (if not already tried)
    if not use_anthropic and anthropic_key:
        log.info("initializing_llm", provider="anthropic", mode="last_resort")
        return ChatAnthropic(
            model="claude-3-5-sonnet-20240620",
            anthropic_api_key=anthropic_key,
            temperature=0
        )

    raise ValueError("No LLM provider configured. Please set ANTHROPIC_API_KEY or OPENROUTER_API_KEY.")
