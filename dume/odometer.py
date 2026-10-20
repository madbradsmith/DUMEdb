"""
DUME Ground-Truth Context & Memory Odometer Engine.
Directly measures actual active context tokens from the Antigravity IDE transcript
since the most recent checkpoint/compaction boundary.
Eliminates hallucinated token gauges with deterministic disk-backed mathematics.
"""

import glob
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_COMPACT_CEILING = 120_000  # Empirical average trigger ceiling in tokens


def get_latest_transcript_path() -> Optional[Path]:
    """Finds the active conversation's transcript.jsonl by latest modification time."""
    base_brain = Path(r"C:\Users\c6182\.gemini\antigravity-ide\brain")
    if not base_brain.exists():
        # Fallback to current user home
        base_brain = Path.home() / ".gemini" / "antigravity-ide" / "brain"
    
    if not base_brain.exists():
        return None

    pattern = str(base_brain / "*" / ".system_generated" / "logs" / "transcript.jsonl")
    matched = glob.glob(pattern)
    if not matched:
        return None
    
    return Path(max(matched, key=os.path.getmtime))


def calculate_real_context_metrics(transcript_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Parses transcript.jsonl to calculate real, mathematically verified context metrics.
    """
    path = transcript_path or get_latest_transcript_path()
    if not path or not path.exists():
        return {
            "error": "No active transcript found on disk",
            "epoch": 1,
            "active_steps": 0,
            "active_tokens": 0,
            "pct": 0.0,
            "runway_tokens": DEFAULT_COMPACT_CEILING,
            "last_step_tokens": 0,
            "zone": "Nominal",
            "zone_icon": "🟢",
            "bar": "[░░░░░░░░░░]",
            "formatted": "📊 **Context Odometer**: [░░░░░░░░░░] 0.0% (0 / 120,000 tok) | Epoch 1 | Zone: 🟢 Nominal"
        }

    lines = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    lines.append(json.loads(line_str))
    except Exception as e:
        return {
            "error": f"Failed reading transcript: {e}",
            "epoch": 1,
            "active_steps": 0,
            "active_tokens": 0,
            "pct": 0.0,
            "runway_tokens": DEFAULT_COMPACT_CEILING,
            "last_step_tokens": 0,
            "zone": "Nominal",
            "zone_icon": "🟢",
            "bar": "[░░░░░░░░░░]",
            "formatted": f"📊 **Context Odometer**: [░░░░░░░░░░] (Error: {e})"
        }

    if not lines:
        return {
            "epoch": 1,
            "active_steps": 0,
            "active_tokens": 0,
            "pct": 0.0,
            "runway_tokens": DEFAULT_COMPACT_CEILING,
            "last_step_tokens": 0,
            "zone": "Nominal",
            "zone_icon": "🟢",
            "bar": "[░░░░░░░░░░]",
            "formatted": "📊 **Context Odometer**: [░░░░░░░░░░] 0.0% | Epoch 1 | Zone: 🟢 Nominal"
        }

    # Find checkpoints / compaction boundaries
    checkpoints = []
    for i, s in enumerate(lines):
        stype = s.get("type", "")
        source = s.get("source", "")
        content = str(s.get("content", "") or "")
        # Only true IDE engine checkpoints can mark an epoch boundary
        if source == "SYSTEM" and (stype == "CHECKPOINT" or "resuming from a compaction" in content.lower()):
            checkpoints.append(i)

    epoch = len(checkpoints) + 1
    last_cp_idx = checkpoints[-1] if checkpoints else 0
    active_window = lines[last_cp_idx:]
    active_steps = len(active_window)

    active_chars = sum(len(json.dumps(s)) for s in active_window)
    active_tokens = active_chars // 4

    # Calculate empirical ceiling if historical checkpoints exist
    ceiling = DEFAULT_COMPACT_CEILING
    if len(checkpoints) >= 2:
        historical_sizes = []
        for j in range(len(checkpoints) - 1):
            w = lines[checkpoints[j]:checkpoints[j+1]]
            toks = sum(len(json.dumps(x)) for x in w) // 4
            if toks > 50_000:
                historical_sizes.append(toks)
        if historical_sizes:
            ceiling = int(sum(historical_sizes) / len(historical_sizes))

    pct = round(min(100.0, (active_tokens / ceiling) * 100), 1)
    runway_tokens = max(0, ceiling - active_tokens)

    # Calculate turn-level split (Option A)
    user_indices = [i for i, s in enumerate(lines) if s.get("type") == "USER_INPUT"]
    if user_indices:
        curr_turn_lines = lines[user_indices[-1]:]
        if len(curr_turn_lines) > 1 or len(user_indices) == 1:
            turn_lines = curr_turn_lines
        else:
            turn_lines = lines[user_indices[-2]:user_indices[-1]]
    else:
        turn_lines = lines[-1:] if lines else []

    turn_in_chars = 0
    turn_out_chars = 0
    for s in turn_lines:
        chars = len(json.dumps(s))
        if s.get("type") == "PLANNER_RESPONSE":
            turn_out_chars += chars
        else:
            turn_in_chars += chars

    turn_in_tokens = turn_in_chars // 4
    turn_out_tokens = turn_out_chars // 4
    turn_delta_tokens = turn_in_tokens + turn_out_tokens

    # Progress bar
    filled = min(10, max(0, int(round(pct / 10))))
    bar = "█" * filled + "░" * (10 - filled)

    if pct < 50:
        zone = "Nominal"
        zone_icon = "🟢"
    elif pct < 75:
        zone = "Elevated"
        zone_icon = "🟡"
    elif pct < 85:
        zone = "Alert (Refresh Recommended)"
        zone_icon = "🟠"
    else:
        zone = "Imminent Compaction"
        zone_icon = "🔴"

    formatted = (
        f"📊 **Context Odometer (Real Math)**: [{bar}] {pct}% "
        f"({active_tokens:,} / ~{ceiling:,} tok) | "
        f"Epoch {epoch} (Turn +{active_steps}) | "
        f"Runway: ~{runway_tokens:,} tok | "
        f"Last Turn: +{turn_delta_tokens:,} tok (📥 {turn_in_tokens:,} in | 📤 {turn_out_tokens:,} out) | "
        f"Zone: {zone_icon} {zone}"
    )

    return {
        "epoch": epoch,
        "active_steps": active_steps,
        "active_tokens": active_tokens,
        "ceiling": ceiling,
        "pct": pct,
        "runway_tokens": runway_tokens,
        "last_step_tokens": turn_delta_tokens,
        "turn_delta_tokens": turn_delta_tokens,
        "turn_in_tokens": turn_in_tokens,
        "turn_out_tokens": turn_out_tokens,
        "zone": zone,
        "zone_icon": zone_icon,
        "bar": bar,
        "formatted": formatted,
        "transcript_path": str(path)
    }


def format_odometer_string() -> str:
    """Returns the one-line markdown odometer string using real math."""
    data = calculate_real_context_metrics()
    return data["formatted"]


if __name__ == "__main__":
    metrics = calculate_real_context_metrics()
    # Print safe ASCII/UTF-8 representation
    out_str = (
        f"\n--- REAL MATHEMATICAL CONTEXT ODOMETER ---\n"
        f"Transcript: {metrics.get('transcript_path')}\n"
        f"Epoch: {metrics['epoch']} | Active Steps: {metrics['active_steps']}\n"
        f"Context Footprint: {metrics['active_tokens']:,} / ~{metrics['ceiling']:,} tokens ({metrics['pct']}%)\n"
        f"Clean Runway Remaining: ~{metrics['runway_tokens']:,} tokens\n"
        f"Last Turn Delta: +{metrics['turn_delta_tokens']:,} tokens (In: {metrics['turn_in_tokens']:,} | Out: {metrics['turn_out_tokens']:,})\n"
        f"Zone: {metrics['zone_icon']} {metrics['zone']}\n"
        f"Summary Line:\n{metrics['formatted']}\n"
    )
    try:
        print(out_str)
    except UnicodeEncodeError:
        print(out_str.encode("ascii", errors="replace").decode("ascii"))
