import os
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List

DUME_SYSTEM_PROMPT = """You are DUME, a deterministic unit-record memory engine assistant.
Always observe the DUME state registers provided at the beginning of the turn prefix [DUME_STATE ...].
Keep responses focused, concise, and grounded in active state registers.
"""

class GeminiSynthesizer:
    """Cloud Synthesizer using Google Gemini API."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(self, prompt: str, system_prompt: Optional[str] = None, custom_key: Optional[str] = None) -> str:
        key = custom_key or self.api_key
        if not key:
            return "[Gemini API key required. Please enter your GEMINI_API_KEY in the Web UI setting.]"

        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-flash"
        ]
        sys_msg = system_prompt or DUME_SYSTEM_PROMPT
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{sys_msg}\n\n{prompt}"}]}
            ]
        }
        
        last_error = ""
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            try:
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                    return str(data)
            except urllib.error.HTTPError as e:
                last_error = f"[Gemini API Error {e.code}]: {e.read().decode('utf-8')}"
                if e.code == 404:
                    continue
                return last_error
            except Exception as e:
                return f"[Gemini API Error]: {str(e)}"
        return last_error


class DUMEFastSynthesizer:
    """Deterministic High-Speed DUME Synthesizer."""
    def __init__(self):
        self.name = "DUME Fast Synthesizer"

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt: Optional[str] = None, custom_key: Optional[str] = None) -> str:
        state_ctx = ""
        if "[DUME_STATE" in prompt:
            try:
                state_ctx = prompt.split("[DUME_STATE")[1].split("[/DUME_STATE]")[0].strip()
            except Exception:
                pass

        user_msg = prompt.strip()
        if "User:" in user_msg:
            user_msg = user_msg.split("User:")[-1].split("Assistant:")[0].strip()

        if state_ctx:
            return f"Received: '{user_msg}'. Active state registers [{state_ctx}]. Grounded and standing by."

        return f"Received: '{user_msg}'. DUME Engine active. Standing by for requests."


class HybridSynthesizer:
    """
    Hybrid Multi-Provider Synthesizer Manager.
    """
    def __init__(self):
        self.gemini = GeminiSynthesizer()
        self.fast_stub = DUMEFastSynthesizer()

    def is_available(self) -> bool:
        return True

    def get_active_provider_name(self, provider: Optional[str] = None, custom_key: Optional[str] = None) -> str:
        return "External Client / Local Proxy"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> str:
        return "[SYSTEM] No agent connected. Route requests via proxy at http://localhost:8090/v1 to ground prompts in active state registers."


class OllamaSynthesizer(HybridSynthesizer):
    """Backwards compatibility alias for OllamaSynthesizer."""
    pass
