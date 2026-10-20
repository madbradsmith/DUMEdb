import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union

from dume.intake.scrubber import EnterpriseScrubber

ASSETS_ERROR_DIR = Path.home() / ".dume" / "assets" / "errors"


def ensure_errors_dir() -> Path:
    """Ensures ~/.dume/assets/errors directory exists."""
    ASSETS_ERROR_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_ERROR_DIR


class ErrorReducer:
    """
    Sentry / Datadog / APM Error Cluster Reducer.
    Extracts normalized exception signatures, scrubs sensitive traces, emits markdown cards
    to ~/.dume/assets/errors/ERR_{FINGERPRINT}.md, and updates DUMEdb error registers.
    """

    @classmethod
    def compute_fingerprint(cls, error_class: str, failing_method: str) -> str:
        """Computes deterministic 8-character hex fingerprint for error cluster."""
        raw = f"{error_class.strip()}::{failing_method.strip()}".encode("utf-8")
        hash_hex = hashlib.blake2b(raw, digest_size=4).hexdigest().upper()
        return f"ERR_{hash_hex}"

    @classmethod
    def reduce_error_payload(
        cls,
        raw_payload: Union[str, Dict[str, Any]],
        entity_id: str = "MadBrad-Nostra-01"
    ) -> Tuple[Dict[str, Any], str]:
        """
        Processes APM / Sentry payload, generates Error Fingerprint Markdown card, and returns
        (registers_dict, asset_path).
        """
        ensure_errors_dir()

        # Parse JSON or fallback text
        data: Dict[str, Any] = {}
        if isinstance(raw_payload, str):
            try:
                data = json.loads(raw_payload)
            except Exception:
                data = {"stacktrace": raw_payload, "exception": {"type": "RuntimeError", "value": raw_payload}}
        elif isinstance(raw_payload, dict):
            data = raw_payload
        else:
            data = {"stacktrace": str(raw_payload)}

        # Sanitize dictionary
        sanitized_data = EnterpriseScrubber.sanitize_dict(data)

        # Extract Error Class
        exc_data = sanitized_data.get("exception") or {}
        if isinstance(exc_data, list) and len(exc_data) > 0:
            exc_data = exc_data[0]
        
        error_class = (
            exc_data.get("type") or
            sanitized_data.get("error_class") or
            sanitized_data.get("type") or
            "UnhandledException"
        ).strip()

        # Extract Failing Method
        failing_method = (
            sanitized_data.get("failing_method") or
            sanitized_data.get("culprit") or
            sanitized_data.get("transaction") or
            "unknown_frame"
        ).strip()

        # Extract 24h Count
        try:
            count_24h = int(sanitized_data.get("count_24h") or sanitized_data.get("count") or 1)
        except Exception:
            count_24h = 1

        # Compute Fingerprint
        fingerprint = (sanitized_data.get("fingerprint") or cls.compute_fingerprint(error_class, failing_method)).strip()

        # Format Stacktrace & Breadcrumbs
        raw_stack = (
            sanitized_data.get("stack_trace") or
            sanitized_data.get("stacktrace") or
            sanitized_data.get("logentry") or
            exc_data.get("value") or
            "No stacktrace provided."
        )
        if isinstance(raw_stack, (dict, list)):
            raw_stack = json.dumps(raw_stack, indent=2)

        scrubbed_stack = EnterpriseScrubber.sanitize_text(str(raw_stack))

        user_context = (
            sanitized_data.get("user_email") or
            sanitized_data.get("user") or
            "N/A"
        )
        scrubbed_user = EnterpriseScrubber.sanitize_text(str(user_context))

        breadcrumbs = sanitized_data.get("breadcrumbs") or []
        b_text = ""
        if breadcrumbs:
            b_items = []
            for b in breadcrumbs:
                if isinstance(b, dict):
                    msg = b.get("message") or b.get("category") or str(b)
                    b_items.append(f"- `[{b.get('timestamp', '--')}]` {EnterpriseScrubber.sanitize_text(str(msg))}")
                else:
                    b_items.append(f"- {EnterpriseScrubber.sanitize_text(str(b))}")
            b_text = "\n".join(b_items)
        else:
            b_text = "- No breadcrumbs captured."

        filename = f"{fingerprint}.md"
        card_path = ASSETS_ERROR_DIR / filename

        md_content = f"""# Error Fingerprint: {fingerprint}

**Exception Class**: `{error_class}`  
**Failing Method**: `{failing_method}`  
**24h Cluster Count**: `{count_24h}`  
**Affected User**: `{scrubbed_user}`  

---

## Sanitized Stack Trace
```
{scrubbed_stack}
```

---

## Breadcrumbs & Event Log
{b_text}
"""

        with open(card_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        registers = {
            "ERROR_CLASS": error_class,
            "ERROR_FINGERPRINT": fingerprint,
            "ERROR_COUNT_24H": count_24h,
            "FAILING_METHOD": failing_method,
            "ERROR_CARD_PATH": str(card_path)
        }

        return registers, str(card_path)
