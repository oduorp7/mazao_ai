
import os
import sys
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

def test_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC: FAIL - No key")
        return
    try:
        llm = ChatAnthropic(model="claude-3-5-sonnet-20240620", anthropic_api_key=key, timeout=10)
        res = llm.invoke([HumanMessage(content="Say OK")])
        print(f"ANTHROPIC: PASS - {res.content.strip()}")
    except Exception as e:
        print(f"ANTHROPIC: FAIL - {type(e).__name__}: {str(e)}")

def test_openrouter():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER: FAIL - No key")
        return
    try:
        llm = ChatOpenAI(
            model="deepseek/deepseek-chat",
            openai_api_key=key,
            openai_api_base="https://openrouter.ai/api/v1",
            timeout=10,
            default_headers={"X-Title": "Mazao AI Test"}
        )
        res = llm.invoke([HumanMessage(content="Say OK")])
        print(f"OPENROUTER: PASS - {res.content.strip()}")
    except Exception as e:
        print(f"OPENROUTER: FAIL - {type(e).__name__}: {str(e)}")

def test_mistral():
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        print("MISTRAL: FAIL - No key")
        return
    try:
        llm = ChatOpenAI(
            model="open-mistral-nemo",
            openai_api_key=key,
            openai_api_base="https://api.mistral.ai/v1",
            timeout=10
        )
        res = llm.invoke([HumanMessage(content="Say OK")])
        print(f"MISTRAL: PASS - {res.content.strip()}")
    except Exception as e:
        print(f"MISTRAL: FAIL - {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    print("--- Starting Provider Tests ---")
    test_anthropic()
    test_openrouter()
    test_mistral()
    print("--- Tests Finished ---")
