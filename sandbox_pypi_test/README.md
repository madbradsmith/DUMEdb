# DUMEdb - Hardware-Aligned Zero-Copy Byte-Structured Memory Engine

DUMEdb is a high-performance, hardware-aligned memory engine with discrete 32-byte active state registers, LMDB persistence, and an OpenAI-compatible proxy gateway for LLM memory grounding.

## Quick Start

### 1. Installation
```bash
pip install -e .
```

### 2. Run Server & Web Inspector
```bash
dumedb
```

Console Output:
```plaintext
=======================================================
🚀 DUMEdb Studio v1 is Live!
🔗 Inspector UI: http://localhost:8090/inspector/index.html
⚡ Proxy Gateway: http://localhost:8090/v1
=======================================================
```

### 3. Connect External Agent / LLM Client
Point any OpenAI-compatible client (LangChain, LlamaIndex, AutoGen, curl) to:
- **Base URL**: `http://localhost:8090/v1`
- **API Key**: `dume-local`
- **Header**: `X-Entity-ID: DemoUser-01`
