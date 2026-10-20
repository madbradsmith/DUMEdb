import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union

from dume.intake.scrubber import EnterpriseScrubber

ASSETS_INCIDENT_DIR = Path.home() / ".dume" / "assets" / "incidents"


def ensure_incidents_dir() -> Path:
    """Ensures ~/.dume/assets/incidents directory exists."""
    ASSETS_INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_INCIDENT_DIR


class IncidentReducer:
    """
    ServiceNow / Jira Incident & Postmortem Reducer.
    Extracts root cause analyses and verified workarounds, scrubs sensitive data,
    emits markdown cards to ~/.dume/assets/incidents/{INCIDENT_ID}.md,
    and updates DUMEdb active incident state registers.
    """

    @classmethod
    def reduce_incident_payload(
        cls,
        raw_payload: Union[str, Dict[str, Any]],
        entity_id: str = "MadBrad-Nostra-01"
    ) -> Tuple[Dict[str, Any], str]:
        """
        Processes ServiceNow/Jira payload, generates Incident Postmortem Markdown card, and returns
        (registers_dict, asset_path).
        """
        ensure_incidents_dir()

        # Parse JSON or fallback text
        data: Dict[str, Any] = {}
        if isinstance(raw_payload, str):
            try:
                data = json.loads(raw_payload)
            except Exception:
                data = {"summary": "Incident Postmortem", "description": raw_payload}
        elif isinstance(raw_payload, dict):
            data = raw_payload
        else:
            data = {"description": str(raw_payload)}

        # Sanitize dictionary
        sanitized_data = EnterpriseScrubber.sanitize_dict(data)

        # Incident ID & Title
        inc_id = str(
            sanitized_data.get("incident_id") or
            sanitized_data.get("ticket_id") or
            sanitized_data.get("key") or
            sanitized_data.get("id") or
            "INC_9001"
        ).strip().upper()
        if not inc_id.startswith("INC"):
            inc_id = f"INC_{inc_id}"

        inc_title = str(sanitized_data.get("title") or "System Outage").strip()

        # Severity
        severity = str(sanitized_data.get("severity") or sanitized_data.get("priority") or "SEV-2").strip().upper()

        # Root Cause & Workaround
        root_cause = str(
            sanitized_data.get("root_cause") or
            sanitized_data.get("rca") or
            sanitized_data.get("summary") or
            "Unidentified resource constraint or network timeout"
        ).strip()

        workaround_status = str(
            sanitized_data.get("workaround_status") or
            sanitized_data.get("status") or
            "VERIFIED"
        ).strip().upper()

        workaround = str(
            sanitized_data.get("workaround") or
            sanitized_data.get("resolution") or
            sanitized_data.get("runbook") or
            "Restart process worker and clear scratchpad cache."
        ).strip()

        details = str(
            sanitized_data.get("details") or
            sanitized_data.get("description") or
            sanitized_data.get("postmortem") or
            "No additional postmortem details provided."
        ).strip()

        filename = f"{inc_id}.md"
        card_path = ASSETS_INCIDENT_DIR / filename

        md_content = f"""# Incident Postmortem: {inc_id} - {EnterpriseScrubber.sanitize_text(inc_title)}

**Severity**: `{severity}`  
**Workaround Status**: `{workaround_status}`  
**Date**: `{sanitized_data.get('created_at', '2026-09-05')}`  

---

## Root Cause
{EnterpriseScrubber.sanitize_text(root_cause)}

## Verified Workaround / Runbook
{EnterpriseScrubber.sanitize_text(workaround)}

---

## Detailed Postmortem
{EnterpriseScrubber.sanitize_text(details)}
"""

        with open(card_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        registers = {
            "ACTIVE_INCIDENT": inc_id,
            "SEVERITY": severity,
            "ROOT_CAUSE": root_cause[:64],
            "WORKAROUND_STATUS": workaround_status,
            "INCIDENT_PATH": str(card_path)
        }

        return registers, str(card_path)
