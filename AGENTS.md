# DUMEdb Workspace Agent Rules

## Mandatory Wake Protocol
1. **Zero-Turn Orientation & Service Auto-Start**: When starting a session, receiving a greeting, a status request ("catch me up", "wake", "status"), or the wake phrase **"Box is the game"**, you MUST immediately:
   a. Call the `cabinet_wake` tool on the `dumedb` MCP server.
   b. Launch/verify the background services: Ensure `python the_table/crawler.py` is running as an IDE background daemon task (`IsDaemon=true`, toolSummary: "The Table Mobile Companion Crawler") so The Table companion is live in the IDE task monitor and mobile messages from Brad's phone are crawled seamlessly with zero manual startup.
2. **No Filesystem Rummaging**: Do NOT search the filesystem, run ripgrep, or inspect directories to reconstruct session state. DUMEdb and The Cabinet hold the orientation.
3. **Session Handoff**: When a session reaches completion or context limits, call `cabinet_refresh` with the summary, next moves, and files touched to write the odometer for the next instance.
4. **Context Meter & Bloat Watch (Real Math)**: At the bottom of every message to the operator, run or evaluate the Ground-Truth Context Odometer using `dume.odometer` (measuring actual post-compaction JSON payload tokens from `transcript.jsonl` on disk). NEVER hallucinate, estimate, or hardcode a fake percentage.
   Format:
   `---`
   `📊 **Context Odometer (Real Math)**: [██░░░░░░░░] <pct>% (<active_tokens> / ~<ceiling> tok) | Epoch <epoch> (Turn +<steps>) | Runway: ~<runway> tok | Last Turn: +<delta> tok (📥 <in> in | 📤 <out> out) | Zone: <icon> <zone>`
   If context consumption reaches >= 75% (~90,000 tokens), warn the operator immediately and trigger `cabinet_refresh` to hand off cleanly before auto-compaction occurs.
5. **Compaction Detection Alert**: Whenever an IDE auto-compaction occurs (indicated by an epoch increment, resuming from a compaction, or working context percentage dropping between turns), the Sentinel MUST explicitly alert the operator:
   `⚠️ **DUMEdb Sentinel Alert: Context Compaction Event Detected**`
   `IDE context auto-compaction occurred. Session transitioned to Epoch <epoch>. Working context was condensed to <active_tokens> tok (<pct>%), with historical transcript safely preserved on disk.`
