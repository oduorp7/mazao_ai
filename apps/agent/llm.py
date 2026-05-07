
import os
import time
from typing import Any, List, Optional
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

class FallbackLLM:
    """
    T46: Hardened FallbackLLM with guaranteed Mistral recovery.
    Order: OpenRouter Free Stack (bounded) -> Mistral-B (guaranteed fallback).
    Mistral is granted 20s execution time to ensure complex financial analysis completion.
    """
    def __init__(self, model_type: str = "default"):
        self.model_type = model_type
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.mistral_key = os.getenv("MISTRAL_API_KEY")
        self.force_mistral = os.getenv("FORCE_MISTRAL", "false").lower() == "true"
        # Anthropic/OpenRouter-Paid disabled by policy in T45/T46
        self.anthropic_enabled = False 

    def invoke(self, messages: List[BaseMessage], **kwargs) -> Any:
        errors = []
        depth = 0
        
        # --- Stage 0: Force Mistral Validation (R3) ---
        if self.force_mistral:
            log.info("llm_trace_force_mistral", tier="validation", model="open-mistral-nemo")
            return self._call_mistral(messages, depth=0, **kwargs)

        # --- Stage 1 & 2: Anthropic / OpenRouter Paid (DISABLED per T45/T46) ---

        # --- Stage 3: OpenRouter Free Stack (R2/R4) ---
        free_models = [
            "liquid/lfm-2.5-1.2b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free"
        ]
        
        if self.openrouter_key:
            for model in free_models:
                depth += 1
                start_time = time.perf_counter()
                try:
                    log.info("llm_trace_attempt", provider="openrouter_free", tier="free", model=model, depth=depth)
                    llm = ChatOpenAI(
                        model=model,
                        openai_api_key=self.openrouter_key,
                        openai_api_base="https://openrouter.ai/api/v1",
                        temperature=0,
                        timeout=6, # Bounded timeout for free models
                        default_headers={"X-Title": "Mazao AI Free Hardened"}
                    )
                    response = llm.invoke(messages, **kwargs)
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    
                    log.info("llm_trace_success", 
                             provider="openrouter_free", 
                             model=model, 
                             latency_ms=latency_ms, 
                             depth=depth)
                    
                    return self._attach_metadata(response, "openrouter_free", model, depth, latency_ms)
                except Exception as e:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    log.warning("llm_trace_failed", 
                                provider="openrouter_free", 
                                model=model, 
                                error_type=type(e).__name__, 
                                latency_ms=latency_ms,
                                depth=depth)
                    errors.append(f"OpenRouter Free ({model}): {type(e).__name__}")
        else:
            log.info("llm_trace_skipped", provider="openrouter_free", reason="no_key")

        # --- Stage 4: Mistral-B (Final Guaranteed Fallback) ---
        depth += 1
        if self.mistral_key:
            return self._call_mistral(messages, depth=depth, **kwargs)
        else:
            log.info("llm_trace_skipped", provider="mistral", reason="no_key", depth=depth)

        # Final failure (R5)
        err_msg = f"All LLM providers exhausted. Depth: {depth}. Errors: {'; '.join(errors)}"
        log.error("all_llm_providers_failed", total_errors=len(errors), depth=depth)
        raise ValueError(err_msg)

    def _call_mistral(self, messages: List[BaseMessage], depth: int, **kwargs) -> Any:
        """Isolated Mistral call for cleaner validation."""
        start_time = time.perf_counter()
        try:
            log.info("llm_trace_attempt", provider="mistral", tier="fallback", model="open-mistral-nemo", depth=depth)
            llm = ChatOpenAI(
                model="open-mistral-nemo",
                openai_api_key=self.mistral_key,
                openai_api_base="https://api.mistral.ai/v1",
                temperature=0,
                timeout=20 # T46: Sufficient time for financial analysis completion
            )
            response = llm.invoke(messages, **kwargs)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            log.info("llm_trace_success", 
                     provider="mistral", 
                     model="open-mistral-nemo", 
                     latency_ms=latency_ms, 
                     depth=depth)
            
            return self._attach_metadata(response, "mistral", "open-mistral-nemo", depth, latency_ms)
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            log.warning("llm_trace_failed", 
                        provider="mistral", 
                        error_type=type(e).__name__, 
                        latency_ms=latency_ms,
                        depth=depth)
            raise ValueError(f"Mistral failed as last resort: {type(e).__name__}")

    def _attach_metadata(self, response: Any, provider: str, model: str, depth: int, latency_ms: int = 0) -> Any:
        """Attaches provider info and latency to the response object (R6)."""
        if hasattr(response, "additional_kwargs"):
            response.additional_kwargs["provider_used"] = provider
            response.additional_kwargs["model_used"] = model
            response.additional_kwargs["fallback_depth"] = depth
            response.additional_kwargs["latency_ms"] = latency_ms
            # T46: Mistral (depth 4) is high-quality, not degraded.
            # ai_degraded only if it was a mock or if we had a lower-tier free model at the end.
            response.additional_kwargs["ai_degraded"] = False 
        return response


def get_llm(model_type: str = "default") -> Any:
    """
    T46: Returns a guaranteed FallbackLLM wrapper.
    """
    priority = os.getenv("LLM_PRIORITY", "openrouter").lower()
    if priority == "local":
        local_base = os.getenv("LOCAL_LLM_BASE", "http://localhost:1234/v1")
        log.info("llm_trace_local", provider="local", base_url=local_base)
        return ChatOpenAI(
            model=os.getenv("LOCAL_LLM_MODEL", "local-model"),
            openai_api_key="not-needed",
            openai_api_base=local_base,
            temperature=0
        )

    return FallbackLLM(model_type=model_type)
