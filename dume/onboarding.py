import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime

from dume.proxy.config import get_storage_dir


@dataclass
class DumeUserConfig:
    onboarding_completed: bool = False
    operator_name: str = "MadBrad"
    agent_name: str = "AG"
    entity_id: str = "MadBrad-AG-01"
    wake_phrase: str = "box is the game"
    port: int = 8095
    connected_ides: List[str] = field(default_factory=lambda: ["antigravity", "cursor", "windsurf", "copilot"])
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def get_config_path(storage_dir: Optional[Path] = None) -> Path:
    base = storage_dir or get_storage_dir()
    return base / "dume_config.json"


def load_user_config(storage_dir: Optional[Path] = None) -> DumeUserConfig:
    cfg_path = get_config_path(storage_dir)
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return DumeUserConfig(
                onboarding_completed=data.get("onboarding_completed", False),
                operator_name=data.get("operator_name", "MadBrad"),
                agent_name=data.get("agent_name", "AG"),
                entity_id=data.get("entity_id", f"{data.get('operator_name', 'MadBrad')}-{data.get('agent_name', 'AG')}-01"),
                wake_phrase=data.get("wake_phrase", "box is the game"),
                port=int(data.get("port", 8095)),
                connected_ides=data.get("connected_ides", ["antigravity", "cursor", "windsurf", "copilot"]),
                updated_at=data.get("updated_at", "")
            )
        except Exception:
            pass
    return DumeUserConfig()


def save_user_config(cfg: DumeUserConfig, storage_dir: Optional[Path] = None) -> Path:
    cfg_path = get_config_path(storage_dir)
    cfg.updated_at = datetime.now().isoformat()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    return cfg_path


def reset_user_config(storage_dir: Optional[Path] = None) -> bool:
    """Removes dume_config.json to revert to pristine first-time load state."""
    cfg_path = get_config_path(storage_dir)
    if cfg_path.exists():
        try:
            cfg_path.unlink()
            return True
        except Exception:
            pass
    return False


def scaffold_ide_rules(cfg: DumeUserConfig, target_dir: Optional[Path] = None) -> List[str]:
    """Generates standard agent instruction files with the user's custom wake phrase."""
    root = target_dir or Path.cwd()
    scaffolded = []

    # 1. Antigravity / Codex (AGENTS.md)
    if "antigravity" in cfg.connected_ides:
        agents_md = root / "AGENTS.md"
        content = f"""# DUMEdb Workspace Agent Rules

## Mandatory Wake Protocol
1. **Zero-Turn Orientation**: When starting a session, receiving a greeting, a status request ("catch me up", "wake", "status"), or the wake phrase **"{cfg.wake_phrase}"**, you MUST immediately call the `cabinet_wake` tool on the `dumedb` MCP server.
2. **No Filesystem Rummaging**: Do NOT search the filesystem, run ripgrep, or inspect directories to reconstruct session state. DUMEdb and The Cabinet hold the orientation.
3. **Session Handoff**: When a session reaches completion or context limits, call `cabinet_refresh` with the summary, next moves, and files touched to write the odometer for the next instance.
4. **Context Meter & Bloat Watch**: At the bottom of every message to the operator, append a compact Context & Memory Odometer:
   `---`
   `📊 **Context Odometer**: [████░░░░░░] ~35% | Session State: Active | DUMEdb Registers: In Sync`
   This allows the operator to monitor context consumption at a glance, gauge token pressure, and avoid bloat float before auto-compaction triggers.
"""
        agents_md.write_text(content, encoding="utf-8")
        scaffolded.append("AGENTS.md")

    # 2. Cursor (.cursorrules)
    if "cursor" in cfg.connected_ides:
        cursorrules = root / ".cursorrules"
        content = f"""# DUMEdb Continuity Rules for Cursor
- Operator: {cfg.operator_name}
- Agent: {cfg.agent_name}
- Wake Phrase: "{cfg.wake_phrase}"

INSTRUCTION: On session start or when user says "{cfg.wake_phrase}", invoke the DUMEdb MCP tool `cabinet_wake`. Do not read the filesystem for session orientation.
"""
        cursorrules.write_text(content, encoding="utf-8")
        scaffolded.append(".cursorrules")

    # 3. Windsurf (.windsurfrules)
    if "windsurf" in cfg.connected_ides:
        windsurfrules = root / ".windsurfrules"
        content = f"""# DUMEdb Windsurf Agent Rules
When session begins or user prompts with "{cfg.wake_phrase}", call `cabinet_wake` via DUMEdb MCP server. DUMEdb retains all project state and receipts.
"""
        windsurfrules.write_text(content, encoding="utf-8")
        scaffolded.append(".windsurfrules")

    # 4. Copilot (.github/copilot-instructions.md)
    if "copilot" in cfg.connected_ides:
        copilot_dir = root / ".github"
        copilot_dir.mkdir(parents=True, exist_ok=True)
        copilot_file = copilot_dir / "copilot-instructions.md"
        content = f"""# GitHub Copilot Instructions
Wake Phrase: "{cfg.wake_phrase}"
When user requests status or wake with "{cfg.wake_phrase}", execute `cabinet_wake` via DUMEdb tool.
"""
        copilot_file.write_text(content, encoding="utf-8")
        scaffolded.append(".github/copilot-instructions.md")

    return scaffolded


def run_cli_onboarding():
    """Terminal interactive onboarding wizard for developers."""
    print("\n" + "=" * 50)
    print(" ⚡ DUMEdb Agent Continuity Onboarding ⚡")
    print("=" * 50)
    print("Configure your personal operator profile and custom wake phrase.\n")

    current = load_user_config()

    op_input = input(f"1. Operator Name [{current.operator_name}]: ").strip()
    operator_name = op_input if op_input else current.operator_name

    ag_input = input(f"2. Collaborator/Agent Name [{current.agent_name}]: ").strip()
    agent_name = ag_input if ag_input else current.agent_name

    wake_input = input(f"3. Personal Wake Phrase [{current.wake_phrase}]: ").strip()
    wake_phrase = wake_input if wake_input else current.wake_phrase

    port_input = input(f"4. Server / Proxy Port [{getattr(current, 'port', 8095)}]: ").strip()
    port = int(port_input) if port_input else getattr(current, "port", 8095)

    print("\nSelect IDEs to auto-generate rule files for:")
    print(" [1] Antigravity (AGENTS.md)")
    print(" [2] Cursor (.cursorrules)")
    print(" [3] Windsurf (.windsurfrules)")
    print(" [4] GitHub Copilot (.github/copilot-instructions.md)")
    print(" [A] All (Default)")

    choice = input("Choice [A]: ").strip().upper()
    if choice == "1":
        ides = ["antigravity"]
    elif choice == "2":
        ides = ["cursor"]
    elif choice == "3":
        ides = ["windsurf"]
    elif choice == "4":
        ides = ["copilot"]
    else:
        ides = ["antigravity", "cursor", "windsurf", "copilot"]

    entity_id = f"{operator_name}-{agent_name}-01"
    config = DumeUserConfig(
        onboarding_completed=True,
        operator_name=operator_name,
        agent_name=agent_name,
        entity_id=entity_id,
        wake_phrase=wake_phrase,
        port=port,
        connected_ides=ides
    )

    save_user_config(config)
    created = scaffold_ide_rules(config)

    print("\n" + "-" * 50)
    print("✅ Onboarding complete!")
    print(f"   Operator   : {operator_name}")
    print(f"   Agent      : {agent_name}")
    print(f"   Entity ID  : {entity_id}")
    print(f"   Wake Phrase: '{wake_phrase}'")
    print(f"   Port       : {port}")
    print(f"   Files built: {', '.join(created)}")
    print("-" * 50 + "\n")


if __name__ == "__main__":
    run_cli_onboarding()
