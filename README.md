# amp — AI Debate Engine

> **Two AIs argue. You get a better answer.**

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/dragon1086/amp-assistant/actions/workflows/test.yml/badge.svg)](https://github.com/dragon1086/amp-assistant/actions)

**Read this in other languages:** [한국어](README.ko.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [Español](README.es.md)

---

## Why amp?

A single AI has blind spots — it trained on the same data, carries the same biases, and tends to give the "safe" answer. **amp runs two independent AIs in parallel, lets them argue, and synthesizes a better answer from both perspectives.**

```
Your question
       │
       ├──────────────────────────────────────┐
       ▼                                      ▼
  Agent A (GPT-5)                      Agent B (Claude)
  [independent analysis]               [independent analysis]
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
                 Reconciler
                      │
                      ▼
         Final Answer  +  CSER score
```

**CSER** (Cross-agent Semantic Entropy Ratio) measures how differently the two AIs thought about your question. Higher CSER → more independent perspectives → better synthesis.

---

## Install

```bash
pip install amp-reasoning
amp init        # interactive setup (~1 min)
```

**Free with OAuth** (no API keys needed — requires ChatGPT Plus + Claude Max subscriptions):
```bash
amp login       # authenticates both providers via browser OAuth
```

**One-line installer:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## Quick Start

```bash
# Ask anything
amp "Should I buy Bitcoin right now?"
amp "React vs Vue in 2026 — which should I pick for a new project?"
amp "What are the real trade-offs between Rust and Go?"

# Deep 4-round debate (takes longer, goes deeper)
amp --mode emergent "Will AGI arrive before 2028?"

# Start MCP server (for Claude Desktop, Cursor, OpenClaw, etc.)
amp serve
```

---

## How It Works

### Default mode — 2-round independent analysis
Agent A and Agent B analyze your question **without seeing each other's answers**.
This guarantees genuine independence → high CSER → better synthesis.

### Emergent mode — 4-round structured debate
```
Round 1:  Agent A analyzes
Round 2:  Agent B challenges A's reasoning
Round 3:  Agent A rebuts B's challenge
Round 4:  Agent B delivers final counterpoint
              └──► Reconciler synthesizes
```

### CSER Gate
If both AIs agree too strongly (CSER < 0.30), amp automatically escalates to 4-round debate
to force more diverse perspectives before synthesizing.

### Knowledge Graph
amp maintains a local knowledge graph (`~/.amp/kg.db`) that accumulates context across
sessions. Over time, amp gets better at your specific domain.

---

## Configuration

```bash
amp init   # interactive wizard
amp setup  # full settings (models, Telegram bot, plugins)
```

Or edit `~/.amp/config.yaml` directly:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2             # gpt-5.2 | gpt-5.4 | gpt-5.4-mini
    reasoning_effort: high     # none | low | medium | high | xhigh

  agent_b:
    provider: anthropic        # fastest with ANTHROPIC_API_KEY
    # provider: anthropic_oauth  # free via Claude OAuth (slower)
    model: claude-sonnet-4-6   # claude-opus-4-6 | claude-haiku-4-6

amp:
  parallel: true      # run Agent A+B in parallel (default: true, ~50% faster)
  timeout: 90         # per-agent timeout in seconds
  kg_path: ~/.amp/kg.db
```

### Provider Options

| Provider | Speed | Cost | Requirement |
|----------|-------|------|-------------|
| `openai` | ⚡⚡⚡ | Paid | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **Free** | ChatGPT Plus/Pro + `amp login` |
| `anthropic` | ⚡⚡⚡ | Paid | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **Free** | Claude Max/Pro + `amp login` |
| `gemini` | ⚡⚡⚡ | Paid | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | Cheap | `DEEPSEEK_API_KEY` |
| `mistral` | ⚡⚡⚡ | Cheap | `MISTRAL_API_KEY` |
| `xai` | ⚡⚡⚡ | Paid | `XAI_API_KEY` |
| `local` | ⚡⚡ | Free | Ollama running |

**Completely free setup (with ChatGPT Plus + Claude Max):**
```bash
amp login
# → Automatically configures openai_oauth × anthropic_oauth
# → $0 API cost
```

---

## MCP Server

Works with Claude Desktop, Cursor, OpenClaw, and any MCP-compatible client:

```bash
amp serve   # starts at http://127.0.0.1:3010
```

Add to your MCP config:
```json
{
  "amp": {
    "url": "http://127.0.0.1:3010"
  }
}
```

Available tools:
| Tool | Description | Typical latency |
|------|-------------|-----------------|
| `analyze` | 2-round independent analysis | 15–30s |
| `debate` | 4-round structured debate | 30–60s |
| `quick_answer` | single-LLM fast answer | ~3s |

---

## Docker

```bash
# Run the MCP server
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

# Or with docker-compose
OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## Python API

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(
    query="Should I use Rust or Go for my backend?",
    context=[],
    config=config,
)

print(result["answer"])
print(f"CSER:       {result['cser']:.2f}")        # how different the two AIs were
print(f"Agreements: {result['agreements']}")       # what both AIs agreed on
print(f"Conflicts:  {result['conflicts']}")        # where they disagreed
```

---

## Performance

Benchmarks on Apple M-series (2026-03, parallel mode):

| Setup | Avg latency | Cost/query |
|-------|-------------|------------|
| GPT-5.2 + Claude Sonnet (API, parallel) | ~18s | $0.03–0.08 |
| GPT-5.2 + Claude OAuth (parallel) | ~35s | ~$0.01 |
| GPT-5.2 + GPT-5.2 (same vendor) | ~15s | $0.02–0.05 |

Parallel A+B execution gives **~50% speedup** vs sequential (v0.1.0+).

---

## Why Cross-Vendor?

GPT and Claude were trained by different companies, on different data, with different
alignment approaches. They genuinely disagree more often than two instances of the same model.
That's the core insight behind amp — **cross-vendor synthesis produces better answers than
single-vendor, even with self-debate prompting**.

Same-vendor pairs (GPT+GPT) also work — amp automatically pushes their personas to
opposite extremes to maximize diversity.

---

## Contributing

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

PRs welcome. Please open an issue first for larger changes.

---

## License

MIT © 2026 amp contributors
