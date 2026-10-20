import re
from typing import Dict, Any, Union

class EnterpriseScrubber:
    """
    Enterprise Secret & PII Scrubber.
    Sanitizes raw text or structured dictionaries prior to storage or LLM ingestion.
    Scrubs:
    - Credit Card PANs & Account Numbers
    - Email Addresses
    - Private IP Ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x) & Internal DNS (.internal, .corp, .local, etc.)
    - Credentials: JWTs, Bearer Tokens, API Keys, Private Keys, Passwords
    """

    # Regex Patterns
    RE_PAN = re.compile(
        r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b|'
        r'\b(?:\d[ -]*?){13,19}\b'
    )
    RE_EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
    
    # Private IP blocks: 10.x.x.x, 172.16-31.x.x, 192.168.x.x
    RE_PRIVATE_IP = re.compile(
        r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}|'
        r'192\.168\.\d{1,3}\.\d{1,3})\b'
    )
    
    # Internal DNS
    RE_INTERNAL_DNS = re.compile(
        r'\b[a-zA-Z0-9-]+\.(?:internal|corp|local|private|lan|domain)\b',
        re.IGNORECASE
    )

    # Private Keys (RSA, EC, Generic)
    RE_PRIVATE_KEY = re.compile(
        r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
    )

    # JWT & Bearer Tokens
    RE_JWT = re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b')
    RE_BEARER = re.compile(r'\bBearer\s+[A-Za-z0-9_\-\.=]+\b', re.IGNORECASE)
    
    # Common API Key Patterns (OpenAI, GitHub, Slack, AWS, generic secret tokens)
    RE_API_KEY = re.compile(
        r'\b(?:sk-[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{20,}|sk_test_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{16})\b'
    )

    # Password / Token Assignment Patterns in logs or code
    RE_KEY_VALUE_SECRET = re.compile(
        r'(?i)\b(password|passwd|api_key|apikey|secret|access_token|auth_token)\b\s*[:=]\s*["\']?([^"\'\s,;]+)["\']?'
    )

    @classmethod
    def scrub(cls, data: Union[str, Dict[str, Any], list]) -> Union[str, Dict[str, Any], list]:
        """Convenience scrub method for text, dict, or list."""
        if isinstance(data, str):
            return cls.sanitize_text(data)
        elif isinstance(data, (dict, list)):
            return cls.sanitize_dict(data)
        return data

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Sanitizes raw string by replacing PII and secrets with safe placeholder tags."""
        if not text or not isinstance(text, str):
            return text or ""

        # 1. Private Keys
        scrubbed = cls.RE_PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", text)

        # 2. JWTs & Bearer Tokens
        scrubbed = cls.RE_JWT.sub("[REDACTED_JWT]", scrubbed)
        scrubbed = cls.RE_BEARER.sub("Bearer [REDACTED_TOKEN]", scrubbed)

        # 3. Known API Keys
        scrubbed = cls.RE_API_KEY.sub("[REDACTED_API_KEY]", scrubbed)

        # 4. Key-Value Secrets (e.g. password="xxx")
        def _kv_sub(match):
            key = match.group(1)
            return f'{key}="[REDACTED_SECRET]"'
        scrubbed = cls.RE_KEY_VALUE_SECRET.sub(_kv_sub, scrubbed)

        # 5. Email Addresses
        scrubbed = cls.RE_EMAIL.sub("[REDACTED_EMAIL]", scrubbed)

        # 6. Private IP addresses & Internal DNS
        scrubbed = cls.RE_PRIVATE_IP.sub("[REDACTED_IP]", scrubbed)
        scrubbed = cls.RE_INTERNAL_DNS.sub("[REDACTED_DNS]", scrubbed)

        # 7. Credit Card PANs (Strict verification check to avoid scrubbing random non-card numbers)
        def _pan_sub(match):
            digits = re.sub(r'\D', '', match.group(0))
            if 13 <= len(digits) <= 19 and cls._luhn_check(digits):
                return "[REDACTED_PAN]"
            return match.group(0)

        scrubbed = cls.RE_PAN.sub(_pan_sub, scrubbed)

        return scrubbed

    @classmethod
    def sanitize_dict(cls, data: Union[Dict[str, Any], list]) -> Union[Dict[str, Any], list]:
        """Recursively sanitizes dictionary strings and list items."""
        if isinstance(data, dict):
            return {k: cls.sanitize_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_dict(item) for item in data]
        elif isinstance(data, str):
            return cls.sanitize_text(data)
        else:
            return data

    @staticmethod
    def _luhn_check(card_num: str) -> bool:
        """Luhn algorithm validation for credit card numbers."""
        total = 0
        reverse_digits = card_num[::-1]
        for i, digit_char in enumerate(reverse_digits):
            d = int(digit_char)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0
