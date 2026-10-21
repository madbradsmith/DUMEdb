# ⚡ DUMEdb (Deterministic Unit-Record Memory Engine)

[![Release](https://img.shields.io/badge/release-v1.1.0-blue.svg?style=flat-square)](https://github.com/madbradsmith/DUMEdb/releases)
[![Python](https://img.shields.io/badge/python-3.9+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![LMDB](https://img.shields.io/badge/storage-LMDB%20Mmap-00ADD8.svg?style=flat-square)](https://symas.com/lmdb/)
[![Latency](https://img.shields.io/badge/read%20latency-%3C%200.8%20%CE%BCs-brightgreen.svg?style=flat-square)](https://github.com/madbradsmith/DUMEdb)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/architecture-Hardware--Aligned%20Zero--Copy-purple.svg?style=flat-square)](https://dumedb.developumaiengine.com)

> **Hardware-aligned, zero-prompt-bloat, byte-structured memory engine and drop-in OpenAI-compatible proxy gateway for autonomous AI agents.**

---

## 🧭 Why DUMEdb?

Modern AI agents suffer from **context rot**, **hallucination creep**, and **quadratic token bills** when state is stuffed into raw conversation transcripts or retrieved fuzzily from high-dimensional vector databases.

```
Traditional Agent Memory (Context Stuffing):
[ System Prompt ] + [ 200 Turn Transcript Dump (85,000 tokens) ] + [ 10 Vector Chunks ] = 💥 Context Rot & High Cost

DUMEdb Memory Substrate:
[ System Prompt ] + [ Discrete 32-Byte Hardware Registers (220 tokens) ] + [ Active Turn ] = ⚡ 100% Deterministic & Instant
```

DUMEdb replaces conversational bloat with **discrete, deterministic 32-byte binary registers** stored in a memory-mapped database (LMDB). AI models read and mutate active state in microseconds with **zero prompt bloat**.

| Feature | Standard Vector DBs (RAG) | Transcript Context Stuffing | ⚡ DUMEdb Substrate |
| :--- | :--- | :--- | :--- |
| **State Nature** | Probabilistic / Semantic Similarity | Conversational String Append | **Hardware-Aligned Discrete Registers** |
| **Lookup Latency** | 20 ms – 150 ms (ANN Index search) | 0 ms (In prompt, but quadratic KV) | **< 0.8 μs (Zero-Copy LMDB Mmap)** |
| **Deterministic Recall** | ❌ No (Prone to Top-K retrieval misses) | ❌ No (Middle-loss attention degradation) | **✅ 100% Exact Opcode Matching** |
| **Token Overhead** | 1,000 – 8,000 tokens per query | 20,000 – 120,000 tokens | **~150 – 350 tokens active state** |
| **Cost per Turn** | High (Heavy token retrieval) | Exponential / Quadratic cost | **Near Zero (Constant KV footprint)** |
| **Offline First** | Sometimes | Yes (Until context exhaustion) | **100% Local, Offline & Self-Contained** |

---

## 🔬 Binary Anatomy: The 32-Byte Unit Record

At the hardware core of DUMEdb is the **Unit Record**—a strictly aligned, 32-byte C-struct packed without pointer indirection:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                  ENTITY_ID (128-bit UUID)                     |
|                                                               |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          OPCODE (uint16)      |         FLAGS (uint16)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     TIMESTAMP (uint32 Unix)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                    VALUE / PAYLOAD (64-bit)                   |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Entity UUID (16 bytes)**: Content-addressed or namespace-isolated actor/agent identity.
- **Opcode (2 bytes)**: Schema-mapped semantic key (`1001-65534`).
- **Flags (2 bytes)**: Bitfield indicating Active state, Float encoding, or Extension Payload pointer.
- **Timestamp (4 bytes)**: Monotonic 32-bit second timestamp.
- **Value (8 bytes)**: Inline immediate data (64-bit Int, IEEE-754 Float, Enum index, or SHA-256 payload hash reference).

---

## ⚡ Core Subsystems

### 1. 📁 Recursive Directory Ingestion Engine
Ingest entire software repositories, project documentation, or knowledge folders into deterministic state registers with a single call:
- **Recursive Directory Crawler**: Discovers and digests file trees while pruning noise (`.git`, `node_modules`, `.venv`, binaries).
- **SHA-256 Content Deduplication**: Identical files across locations are deduplicated in memory.
- **Automatic Opcode Minting**: Novel fields and parameters automatically mint clean, schema-typed opcodes in the `2001-65534` space.
- **Atomic Single-Transaction LMDB Commits**: Thousands of registers are persisted in milliseconds.

### 2. 🔄 OpenAI Universal Proxy Gateway (`/v1`)
Drop-in compatibility with **any** AI client: Cursor, Claude Desktop, VS Code (Cline), OpenWebUI, LangChain, or raw cURL.
- Intercepts requests pointing to `http://localhost:8095/v1`.
- Injects deterministic state registers (`[DUME_STATE ...]`) into the active prompt prefix with microsecond speed.
- Passes streaming completions transparently to upstream models (Ollama, vLLM, Groq, OpenAI, Anthropic).
- Automatically scribes assistant mutations in the background.

### 3. 🎛️ Dual-View Web Inspector
A visual cockpit for inspecting and managing agent memory in real time:
- **Dual View**: Switch between interactive cards and raw hardware hex dumps.
- **Real-Time WebSocket Sync**: Live updates as agents commit mutations.
- **Directory Ingestion Modal**: Instant folder crawling with one click.
- **Token Telemetry & KV-Cache Runway**: Real-time context monitoring.

### 4. 🗄️ The Cabinet
Autonomous session orientation ledger that maintains agent continuity across restarts, compacting work logs and next moves to eliminate "catch-me-up" context waste.

---

## 🚀 Quick Start (60 Seconds)

### 1. Installation

```bash
# Clone repository
git clone https://github.com/madbradsmith/DUMEdb.git
cd DUMEdb

# Install editable package
pip install -e .
```

### 2. Start the Engine & Inspector

```bash
# Start server (default port: 8095)
python -m dume --port 8095

# Or on Windows:
Start_DUMEdb_UI.bat

# Or on macOS/Linux:
./start_dumedb.sh
```

Console Output:
```plaintext
=======================================================
🚀 DUMEdb Studio v1.1.0 is Live!
🔗 Web Inspector: http://localhost:8095/inspector/index.html
⚡ Proxy Gateway: http://localhost:8095/v1
=======================================================
```

Open your browser to: **[http://localhost:8095/inspector/index.html](http://localhost:8095/inspector/index.html)**

---

## 🔌 Connecting to Your Agent Tools

### Cursor / VS Code (Cline / Continue)
Point your model base URL to the DUMEdb local proxy gateway:

```json
{
  "openai.baseUrl": "http://localhost:8095/v1",
  "openai.apiKey": "dume-local"
}
```

### Python SDK / OpenAI Client
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8095/v1",
    api_key="dume-local"
)

response = client.chat.completions.create(
    model="llama3",
    messages=[
        {"role": "user", "content": "What is our current project status?"}
    ],
    extra_headers={"X-Entity-ID": "MadBrad-Nostra-01"}
)

print(response.choices[0].message.content)
```

### Ingest a Directory via CLI / cURL
```bash
# Via cURL
curl -X POST http://localhost:8095/dume/ingest/directory \
  -H "Content-Type: application/json" \
  -H "X-Entity-ID: Project-Alpha" \
  -d '{"directory_path": "C:/Projects/MyAwesomeRepo", "recursive": true}'
```

```python
# Via Python
from dume.intake.directory_reducer import DirectoryReducer

result = DirectoryReducer.reduce_directory("C:/Projects/MyAwesomeRepo")
print(f"Ingested {result['files_ingested']} files into {result['total_registers_extracted']} registers in {result['duration_ms']}ms.")
```

---

## 📐 Architecture Overview

```
                         ┌────────────────────────────────────────┐
                         │   Autonomous Agent / IDE / Chat UI     │
                         │   (Cursor, Claude Desktop, LangChain)  │
                         └───────────────────┬────────────────────┘
                                             │  OpenAI-Compatible
                                             ▼  HTTP /v1
                         ┌────────────────────────────────────────┐
                         │         DUME Universal Proxy           │
                         │  - Header entity resolution            │
                         │  - Context prefix assembly (<0.8μs)    │
                         │  - Inline directive parser (!set)      │
                         └───────┬────────────────────────┬───────┘
                                 │                        │
               Read/Write Mmap   │                        │ Async Pipeline
                                 ▼                        ▼
     ┌────────────────────────────────────┐    ┌─────────────────────────┐
     │      LMDB Memory Substrate         │    │   Scribe Worker Queue   │
     │  - 32-Byte Unit Records            │    │  - Mutation validation  │
     │  - Multi-version concurrency (MVCC)│    │  - WebSocket broadcast  │
     │  - Zero-copy binary struct unpack  │    └────────────┬────────────┘
     └────────────────────────────────────┘                 │
                                 ▲                          ▼
                                 │              ┌────────────────────────┐
                                 └──────────────┤  Dynamic Schema Dict   │
                                                │  - 65k Opcode Manager  │
                                                │  - JSON Disk Catalog   │
                                                └────────────────────────┘
```

---

## 🧪 Testing

DUMEdb includes a comprehensive pytest suite covering the core memory engine, LMDB concurrency, schema dictionaries, directory ingestion, and the OpenAI proxy substrate:

```bash
pytest tests/
```

---

## 📄 License

DUMEdb is licensed under the [MIT License](LICENSE). Built for high-performance deterministic agentic computing.
