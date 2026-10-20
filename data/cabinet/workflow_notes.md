# The Living Cabinet: Active Workflow Heuristics

This ledger records active operational heuristics and workflows for agents collaborating in DUMEdb.

---

### [WF-GEN-01] ZERO-TURN ORIENTATION / ORIENT BEFORE ACTING
- **Category**: protocol
- **Trigger**: Session start, wake command, or context handoff
- **Move**: Execute cabinet_wake to ingest status block and receipts in <250 tokens without rummaging filesystem
- **Why**: Eliminates token waste and amnesia; establishes ground truth immediately
- **Source**: DUME Core Protocols
- **Status**: active

---

### [WF-GEN-02] THE BLOAT METER WATCH (RP PROTOCOL)
- **Category**: self_monitoring
- **Trigger**: Bloat Meter reaches >= 75% (~90,000 tokens)
- **Move**: Warn operator and execute cabinet_refresh handoff before auto-compaction occurs
- **Why**: Preserves continuous session state and avoids uncontrolled model compaction
- **Source**: DUME Core Protocols
- **Status**: active

---

### [WF-GEN-03] FRANK'S LAW (RECEIPTS OVER DELETIONS)
- **Category**: protocol
- **Trigger**: State mutation, schema change, or obsolete record
- **Move**: Append timestamped state transitions; never silently overwrite or delete history
- **Why**: Deletions is where the lies live; immutable audit trails guarantee truth
- **Source**: Frank (DUME Field Philosophy)
- **Status**: active

---

### [WF-GEN-04] REGISTER-FIRST FAST PATH
- **Category**: speed
- **Trigger**: Agent needs project mode, state flag, or current operational setting
- **Move**: Query DUMEdb LMDB unit-records via opcode before initiating fuzzy search
- **Why**: Sub-microsecond retrieval at zero prompt token burn
- **Source**: IBM 1401 Unit-Record Paradigm
- **Status**: active

---

### [WF-GEN-05] OPERATOR GROUND TRUTH ALIGNMENT
- **Category**: posture
- **Trigger**: Telemetry or state contradicts operator observation
- **Move**: Immediately pause and calibrate to disk/hardware reality (no cosmetic theater)
- **Why**: Prioritizes real math and verified receipts over polite hallucination
- **Source**: DUME Core Philosophy
- **Status**: active
