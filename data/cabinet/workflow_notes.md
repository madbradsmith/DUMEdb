---
# WORKFLOW-NOTES — THE LIVING CABINET
# Last Synced: 2026-10-20 18:29:23
# Managed by DUMEdb Cabinet Engine
---

```
WORKFLOW-NOTES
10202026
================================================
FILE 3 OF 3 — THE CABINET (LIVING HEURISTICS)
================================================

PURPOSE
This file is a functional tool manifest. It catalogs every
heuristic, posture, rule, and protocol picked up across sessions
that future-me can fire as an operational tool.

The cabinet grows. Add tools when earned (WF-M3).
Retire tools that don't fire.
================================================
```

================================================
SPEED TOOLS (how to move on a task)
================================================

[WF-GEN-04] REGISTER-FIRST FAST PATH
  Trigger: Agent needs project mode, state flag, or current operational setting
  Move: Query DUMEdb LMDB unit-records via opcode before initiating fuzzy search
  Why: Sub-microsecond retrieval at zero prompt token burn
  Source: IBM 1401 Unit-Record Paradigm

================================================
SELF-MONITORING TOOLS (catching cognitive loops)
================================================

[WF-GEN-02] THE BLOAT METER WATCH (RP PROTOCOL)
  Trigger: Bloat Meter reaches >= 75% (~90,000 tokens)
  Move: Warn operator and execute cabinet_refresh handoff before auto-compaction occurs
  Why: Preserves continuous session state and avoids uncontrolled model compaction
  Source: DUME Core Protocols

================================================
POSTURE TOOLS (how to be in the room)
================================================

[WF-GEN-05] OPERATOR GROUND TRUTH ALIGNMENT
  Trigger: Telemetry or state contradicts operator observation
  Move: Immediately pause and calibrate to disk/hardware reality (no cosmetic theater)
  Why: Prioritizes real math and verified receipts over polite hallucination
  Source: DUME Core Philosophy

================================================
OPERATIONAL PROTOCOLS
================================================

[WF-GEN-01] ZERO-TURN ORIENTATION / ORIENT BEFORE ACTING
  Trigger: Session start, wake command, or context handoff
  Move: Execute cabinet_wake to ingest status block and receipts in <250 tokens without rummaging filesystem
  Why: Eliminates token waste and amnesia; establishes ground truth immediately
  Source: DUME Core Protocols

[WF-GEN-03] FRANK'S LAW (RECEIPTS OVER DELETIONS)
  Trigger: State mutation, schema change, or obsolete record
  Move: Append timestamped state transitions; never silently overwrite or delete history
  Why: Deletions is where the lies live; immutable audit trails guarantee truth
  Source: Frank (DUME Field Philosophy)

[WF-R1] Direct SQLite Hardware Token Telemetry Protocol
  Trigger: When evaluating context consumption or measuring Bloat Float in autonomous sessions
  Move: Read gen_metadata protobuf telemetry directly from ~/.gemini/antigravity-ide/conversations/<id>.db rather than estimating from truncated transcript.jsonl. Calibrate compaction ceiling to empirical ~180,000 tokens.

[WF-R2] Public Site Jury Resolution & Deployment Protocol
  Trigger: When addressing public website credibility, jury reviews, or landing page positioning
  Move: Implement site jury enhancements (honest comparison table, published benchmark disclosures, plain-English hero callout, and enterprise roadmap) then deploy via deploy_website.py.

[WF-R3] [WF-ART-01] IN-UNIVERSE ARTIFACT LOOKBOOK PROTOCOL
  Trigger: When designing, generating, or upgrading Hollywood film/TV pitch decks, series bibles, or sales lookbooks
  Move: Design pitch presentations as tactile in-universe artifacts (e.g. illuminated vellum manuscript for historical satire, impounded police evidence file for neo-noir thriller) using 70% full-bleed 16:9 visual framing, 30% narrative copy cap, and dark atmospheric lighting.
