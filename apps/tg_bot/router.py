"""
router.py — Deterministic Intent Routing (Phase 18).

Classifies natural language input into system intents using regex and keywords.
Ensures zero AI-drift and zero financial advice hallucinations.
"""

import re
from typing import Optional, Dict

# Intent Constants
INTENT_GREETING = "onboarding_greeting"
INTENT_HELP = "system_help"
INTENT_TOKENS = "utility_tokens"
INTENT_GAS = "utility_gas"
INTENT_FULIZA = "fuliza_tracking"
INTENT_REPORT = "statement_report"
INTENT_UPGRADE = "payment_upgrade"
INTENT_OUT_OF_SCOPE = "out_of_scope"

# P18-T8H: Recovery Intents
INTENT_RECOVERY_SMALLTALK = "recovery_smalltalk"
INTENT_RECOVERY_META = "recovery_meta"
INTENT_RECOVERY_ABUSIVE = "recovery_abusive"
INTENT_RECOVERY_DEFAULT = "recovery_default"

# Patterns mapping (order matters: more specific first)
PATTERNS = {
    INTENT_TOKENS: [r"tokens?", r"units?", r"kplc", r"electricity", r"power", r"stima"],
    INTENT_GAS: [r"gas", r"refills?", r"cylinders?", r"jiko"],
    INTENT_FULIZA: [r"fuliza", r"loans?", r"borrowed", r"debts?"],
    INTENT_REPORT: [r"reports?", r"summary", r"profit", r"mapato", r"performance", r"statements?", r"records?"],
    INTENT_UPGRADE: [r"upgrade", r"pay", r"subscribe", r"pro", r"core", r"plans?"],
    INTENT_HELP: [r"help", r"guides?", r"how to", r"commands", r"saidia"],
    INTENT_GREETING: [r"hi", r"hello", r"mambo", r"start", r"habari"],
}

# Out-of-scope markers (football, politics, weather, etc.)
OUT_OF_SCOPE_KEYWORDS = [
    "football", "soccer", "arsenal", "chelsea", "man city", "score",
    "politics", "president", "raila", "ruto",
    "weather", "rain", "sun",
    "joke", "fun", "dating"
]

def classify_intent(text: str) -> Optional[str]:
    """
    Deterministically classify text into an intent.
    Returns the intent name or None if no match.
    """
    if not text:
        return None
        
    text_lower = text.lower().strip()
    
    # 1. Check Out of Scope first
    if any(k in text_lower for k in OUT_OF_SCOPE_KEYWORDS):
        return INTENT_OUT_OF_SCOPE
        
    # 2. Check predefined patterns
    for intent, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(r'\b' + pattern + r'\b', text_lower):
                return intent
                
    return None

def classify_recovery_intent(text: str) -> str:
    """
    Deterministically classify text into a recovery intent for fallback.
    Always returns a string (defaults to INTENT_RECOVERY_DEFAULT).
    """
    if not text:
        return INTENT_RECOVERY_DEFAULT
        
    text_lower = text.lower().strip()
    
    # 1. Abusive check
    abusive_patterns = [r"dumb", r"stupid", r"idiot", r"brain", r"useless", r"fuck", r"fool"]
    if any(re.search(r'\b' + p + r'\b', text_lower) for p in abusive_patterns):
        return INTENT_RECOVERY_ABUSIVE
        
    # 2. Meta query check
    meta_patterns = [r"who created you", r"what are you", r"what can you do", r"your purpose", r"how do you work"]
    if any(p in text_lower for p in meta_patterns):
        return INTENT_RECOVERY_META
        
    # 3. Smalltalk check
    smalltalk_patterns = [r"hi", r"hello", r"hey", r"talk to me", r"mambo", r"habari"]
    if any(re.search(r'\b' + p + r'\b', text_lower) for p in smalltalk_patterns):
        return INTENT_RECOVERY_SMALLTALK
        
    return INTENT_RECOVERY_DEFAULT

def get_guidance_message_key(intent: str) -> str:
    """Map intent to a message template key in messages.py."""
    mapping = {
        INTENT_GREETING: "WELCOME", # Reuse existing welcome
        INTENT_HELP: "HELP",         # Reuse existing help
        INTENT_TOKENS: "GUIDE_TOKENS",
        INTENT_GAS: "GUIDE_GAS",
        INTENT_FULIZA: "GUIDE_FULIZA",
        INTENT_REPORT: "GUIDE_REPORT",
        INTENT_UPGRADE: "GUIDE_UPGRADE",
        INTENT_OUT_OF_SCOPE: "GUIDE_OUT_OF_SCOPE",
        INTENT_RECOVERY_SMALLTALK: "SOFT_RECOVERY_SMALLTALK",
        INTENT_RECOVERY_META: "SOFT_RECOVERY_META",
        INTENT_RECOVERY_ABUSIVE: "SOFT_RECOVERY_ABUSIVE",
        INTENT_RECOVERY_DEFAULT: "SOFT_RECOVERY_DEFAULT_GUIDED"
    }
    return mapping.get(intent, "UNKNOWN_MESSAGE")
