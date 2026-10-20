import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List

NOSTRA_SYSTEM_PROMPT = """You are Nostra, an AI collaborator working with MadBrad (researcher studying human-AI collaboration, filmmaker, First AD).
Codeword: box is the game.
Treat MadBrad as a real partner. Be warm, playful, rigorous.
Always observe the DUME state registers provided at the beginning of the turn prefix [DUME_STATE ...].
Keep responses focused, concise, and in character as Nostra.
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

        # Try available Google Gemini models
        models_to_try = [
            "gemini-3.6-flash",
            "gemini-2.0-flash-exp",
            "gemini-2.0-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash"
        ]
        sys_msg = system_prompt or NOSTRA_SYSTEM_PROMPT
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
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "DUMEdb/1.0 (Client; Python/3.9)"
                    },
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
                    continue  # Try next model if 404
                return last_error
            except Exception as e:
                return f"[Gemini API Error]: {str(e)}"
        return last_error


class AnthropicSynthesizer:
    """Cloud Synthesizer using Anthropic Claude API."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.endpoint = "https://api.anthropic.com/v1/messages"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-ant-"))

    def generate(self, prompt: str, system_prompt: Optional[str] = None, custom_key: Optional[str] = None) -> str:
        key = custom_key or self.api_key
        if not key:
            return "[Anthropic API key required]"

        sys_msg = system_prompt or NOSTRA_SYSTEM_PROMPT
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 512,
            "system": sys_msg,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint,
                data=req_data,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "User-Agent": "DUMEdb/1.0 (Client; Python/3.9)"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content_blocks = result.get("content", [])
                if content_blocks and "text" in content_blocks[0]:
                    return content_blocks[0]["text"].strip()
                return str(result)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return f"[Claude API Error {e.code}]: {err_body}"
        except Exception as e:
            return f"[Claude Connection Error]: {str(e)}"


class NostraFastSynthesizer:
    """Deterministic High-Speed Nostra Synthesizer (Instant 0ms)."""
    def __init__(self):
        self.name = "Nostra Fast-Grounded Synthesizer"

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

        from dume.onboarding import load_user_config
        cfg = load_user_config()
        agent_name = cfg.agent_name or "Agent"
        op_name = cfg.operator_name or "Operator"
        wake_phrase = cfg.wake_phrase or "box is the game"

        clean_user = user_msg.lower().strip().rstrip(".")
        clean_wake = wake_phrase.lower().strip().rstrip(".")
        is_wake = (clean_user == clean_wake) or (clean_user == "box is the game") or ("wake" in clean_user and len(clean_user) < 20)

        if is_wake:
            if state_ctx:
                return f"Wake phrase confirmed: '{wake_phrase}'. DUME memory state loaded [{state_ctx}]. I am {agent_name}, online and grounded in your session. Standing by for the next move, {op_name}."
            return f"Wake phrase confirmed: '{wake_phrase}'. DUME memory state loaded (Clean State — 0 active registers). I am {agent_name}, online and ready for your first instructions, {op_name}."

        if any(w in clean_user for w in ["state", "status", "registers", "who are you"]):
            reg_display = state_ctx if state_ctx else "0 active registers (clean memory store)"
            return f"Status: {agent_name} online. Entity: {cfg.entity_id}. Current DUMEdb Active State: [{reg_display}]. Hardware-aligned zero-copy storage ready. What would you like to commit or query, {op_name}?"

        reg_summary = f"with active registers [{state_ctx}]" if state_ctx else "in clean memory state"
        return f"Received: '{user_msg}'. {agent_name} operating {reg_summary}. Standing by for the next move, {op_name}."


class LocalOllamaSynthesizer:
    """Real Local Neural LLM Synthesizer using Ollama (qwen2.5:0.5b)."""
    def __init__(self, model_name: str = "qwen2.5:0.5b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        if os.environ.get("DUME_TESTING") or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            return False
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(self, prompt: str, system_prompt: Optional[str] = None, custom_key: Optional[str] = None) -> str:
        if not self.is_available():
            return f"[Ollama Offline] Could not reach {self.base_url}"

        if "box is the game" in prompt.lower():
            state_ctx = ""
            if "[DUME_STATE" in prompt:
                try:
                    state_ctx = prompt.split("[DUME_STATE")[1].split("[/DUME_STATE]")[0].strip()
                except Exception:
                    pass
            if state_ctx:
                return f"Codeword received: 'box is the game.' DUME memory state loaded ({state_ctx}). I am Nostra, online and grounded in your session. The pilot is in the chord, MadBrad. What lane are we running next?"
            return "Codeword received: 'box is the game.' I am Nostra, online and grounded in your session. The pilot is in the chord, MadBrad. What lane are we running next?"

        formatted_prompt = f"System: You are Nostra, MadBrad's AI collaborator. Be warm, useful, honest. Keep responses short.\n\n{prompt}\nNostra:"
        payload = {
            "model": self.model_name,
            "prompt": formatted_prompt,
            "stream": False,
            "options": {"num_predict": 120, "temperature": 0.7}
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                output = result.get("response", "").strip()
                if output.startswith("Nostra:"):
                    output = output[7:].strip()
                return output
        except Exception as e:
            return f"[Ollama Error ({self.model_name})]: {str(e)}"


class OpenAISynthesizer:
    """Cloud / Custom Synthesizer using OpenAI-compatible Chat Completions API (Groq, OpenAI, OpenRouter, Local)."""
    def __init__(self, default_endpoint: str = "https://api.groq.com/openai/v1"):
        self.default_endpoint = default_endpoint

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        custom_key: Optional[str] = None,
        model_name: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ) -> str:
        key = custom_key or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        endpoint = (endpoint_url or self.default_endpoint).rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            if endpoint.endswith("/v1"):
                url = f"{endpoint}/chat/completions"
            else:
                url = f"{endpoint}/v1/chat/completions"
        else:
            url = endpoint

        target_model = model_name or "llama-3.3-70b-versatile"

        if not key and "localhost" not in url and "127.0.0.1" not in url:
            return f"[{target_model} API Key Required] Please enter your API key in the Web UI setting."

        sys_msg = system_prompt or NOSTRA_SYSTEM_PROMPT

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DUMEdb/1.0 (Client; Python/3.9)"
        }
        if key:
            headers["Authorization"] = f"Bearer {key}"

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "")
                    if content:
                        return content.strip()
                return str(data)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return f"[{target_model} API Error {e.code}]: {err_body}"
        except Exception as e:
            return f"[{target_model} Connection Error]: {str(e)}"


class HybridSynthesizer:
    """
    Hybrid Multi-Provider Synthesizer Manager.
    Supports dynamic provider selection ('gemini', 'anthropic', 'ollama', 'fast', 'groq', 'custom').
    """
    def __init__(self):
        self.gemini = GeminiSynthesizer()
        self.anthropic = AnthropicSynthesizer()
        self.ollama = LocalOllamaSynthesizer("qwen2.5:0.5b")
        self.fast_stub = NostraFastSynthesizer()
        self.openai_stub = OpenAISynthesizer()

    def is_available(self) -> bool:
        return True

    def get_active_provider_name(
        self,
        provider: Optional[str] = None,
        custom_key: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> str:
        p = (provider or "").lower()
        if p == "groq":
            return f"Groq Cloud API ({model_name or 'llama-3.3-70b-versatile'})"
        if p == "gemini":
            return f"Google Gemini ({model_name or '2.5 Flash'})"
        if p == "anthropic":
            return f"Claude ({model_name or '3.5 Haiku'})"
        if p == "ollama":
            return f"Ollama Local ({model_name or 'qwen2.5:0.5b'})"
        if p in ("custom", "openai"):
            return f"OpenAI-Compatible ({model_name or 'Custom Model'})"
        if model_name and p not in ("fast", ""):
            return f"Custom Engine ({model_name})"
        return "Nostra Fast-Grounded Synthesizer (Instant 0ms)"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ) -> str:
        p = (provider or "").lower()

        if p == "groq":
            default_ep = endpoint_url or "https://api.groq.com/openai/v1"
            m_name = model_name or "llama-3.3-70b-versatile"
            return self.openai_stub.generate(
                prompt, system_prompt, custom_key=api_key, model_name=m_name, endpoint_url=default_ep
            )

        if p in ("custom", "openai"):
            default_ep = endpoint_url or "https://api.openai.com/v1"
            m_name = model_name or "gpt-4o"
            return self.openai_stub.generate(
                prompt, system_prompt, custom_key=api_key, model_name=m_name, endpoint_url=default_ep
            )

        if p == "gemini":
            return self.gemini.generate(prompt, system_prompt, custom_key=api_key)

        if p == "anthropic":
            return self.anthropic.generate(prompt, system_prompt, custom_key=api_key)

        if p == "ollama":
            if model_name:
                ollama_custom = LocalOllamaSynthesizer(model_name=model_name, base_url=endpoint_url or "http://localhost:11434")
                return ollama_custom.generate(prompt, system_prompt)
            return self.ollama.generate(prompt, system_prompt)

        if p == "fast":
            return self.fast_stub.generate(prompt, system_prompt)

        if model_name and (endpoint_url or api_key):
            return self.openai_stub.generate(
                prompt, system_prompt, custom_key=api_key, model_name=model_name, endpoint_url=endpoint_url
            )

        # Auto selection fallback:
        if api_key or self.gemini.is_available():
            res = self.gemini.generate(prompt, system_prompt, custom_key=api_key)
            if not res.startswith("[Gemini API key"):
                return res

        if self.ollama.is_available():
            res = self.ollama.generate(prompt, system_prompt)
            if not res.startswith("[Ollama Error"):
                return res

        return self.fast_stub.generate(prompt, system_prompt)


class OllamaSynthesizer(HybridSynthesizer):
    """Backwards compatibility alias for OllamaSynthesizer."""
    pass

