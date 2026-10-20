import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union

from dume.intake.scrubber import EnterpriseScrubber

ASSETS_ADR_DIR = Path.home() / ".dume" / "assets" / "adrs"


def ensure_adrs_dir() -> Path:
    """Ensures ~/.dume/assets/adrs directory exists."""
    ASSETS_ADR_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_ADR_DIR


class PRReducer:
    """
    GitHub / GitLab PR Reducer & Architectural Decision Record (ADR) Extractor.
    Ingests PR JSON exports or git diff logs, filters routine commits, scrubs secrets/PII,
    emits Markdown ADR cards, and commits diagnostic state pointers to DUMEdb.
    """

    ROUTINE_KEYWORDS = {
        "bump", "style", "typo", "formatting", "chore", "merge",
        "update readme", "clean up", "lint", "v1.0.", "fix typo"
    }

    @classmethod
    def is_routine_commit(cls, text: str) -> bool:
        """Determines if commit message or PR title is a routine bump/typo commit."""
        low = text.lower().strip()
        for kw in cls.ROUTINE_KEYWORDS:
            if kw in low and len(low) < 40:
                return True
        return False

    @classmethod
    def reduce_pr_payload(
        cls,
        raw_payload: Union[str, Dict[str, Any]],
        entity_id: str = "MadBrad-Nostra-01",
        default_module: str = "core_system"
    ) -> Tuple[Dict[str, Any], str]:
        """
        Processes PR payload (JSON or text), generates ADR markdown asset, and returns
        (registers_dict, asset_path).
        """
        ensure_adrs_dir()

        # Parse JSON or fallback text
        data: Dict[str, Any] = {}
        if isinstance(raw_payload, str):
            try:
                data = json.loads(raw_payload)
            except Exception:
                data = {"title": "Pull Request Analysis", "body": raw_payload}
        elif isinstance(raw_payload, dict):
            data = raw_payload
        else:
            data = {"body": str(raw_payload)}

        # Sanitize input
        sanitized_data = EnterpriseScrubber.sanitize_dict(data)
        
        pr_number = str(sanitized_data.get("pr_id") or sanitized_data.get("number") or sanitized_data.get("id") or "101").strip()
        pr_title = str(sanitized_data.get("title") or "Architectural Update").strip()
        pr_body = str(sanitized_data.get("summary") or sanitized_data.get("body") or sanitized_data.get("description") or "").strip()
        author = str(sanitized_data.get("author") or "N/A").strip()
        module = str(sanitized_data.get("module") or sanitized_data.get("component") or default_module).strip().lower()
        module = re.sub(r'[^a-z0-9_]', '_', module)

        # Check commit history if provided
        commits = sanitized_data.get("commits") or []
        meaningful_commits = []
        for c in commits:
            msg = c.get("message") if isinstance(c, dict) else str(c)
            if not cls.is_routine_commit(msg):
                meaningful_commits.append(msg)

        # Extract ADR components
        problem = sanitized_data.get("problem") or "Legacy implementation coupling or performance bottleneck."
        constraint = sanitized_data.get("constraint") or "Must maintain backwards compatibility and sub-0.1ms latency."
        decision = sanitized_data.get("decision") or pr_title + ("\n\n" + pr_body if pr_body else "")
        tradeoff = sanitized_data.get("tradeoff") or "Increased initial memory footprint in exchange for O(1) zero-copy retrieval."

        slug = re.sub(r'[^a-zA-Z0-9]', '_', pr_title.lower())
        slug = re.sub(r'_+', '_', slug).strip('_')[:30] or "architectural_change"

        clean_pr_id = pr_number.upper().replace("PR-", "").replace("PR_", "")
        filename = f"ADR_{clean_pr_id}_{slug}.md"
        card_path = ASSETS_ADR_DIR / filename

        md_content = f"""# ADR-{clean_pr_id}: {pr_title}

**Module**: `{module}`  
**Author**: `{EnterpriseScrubber.sanitize_text(author)}`  
**Status**: `ACCEPTED`  
**Date**: `{sanitized_data.get('created_at', '2026-09-05')}`  

---

## Summary
{EnterpriseScrubber.sanitize_text(pr_body if pr_body else pr_title)}

## Problem
{EnterpriseScrubber.sanitize_text(problem)}

## Constraint
{EnterpriseScrubber.sanitize_text(constraint)}

## Decision
{EnterpriseScrubber.sanitize_text(decision)}

## Trade-Off
{EnterpriseScrubber.sanitize_text(tradeoff)}

---

### Meaningful Commits ({len(meaningful_commits)})
{chr(10).join(f"- {EnterpriseScrubber.sanitize_text(str(c))}" for c in meaningful_commits) if meaningful_commits else "- Initial PR implementation"}
"""

        with open(card_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        adr_key = f"ADR_{pr_number}_{slug.upper()[:16]}"
        registers = {
            "CURRENT_MODULE": module,
            "ACTIVE_ADR": adr_key,
            "ADR_PATH": str(card_path)
        }

        return registers, str(card_path)
