<div align="center">

![amp banner](docs/assets/banner.png)

<h3>Two AIs argue. You get a better answer.</h3>

[![PyPI version](https://img.shields.io/pypi/v/amp-reasoning?color=7c3aed&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Downloads](https://img.shields.io/pypi/dm/amp-reasoning?color=0891b2&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/dragon1086/amp-assistant/test.yml?style=flat-square&label=CI)](https://github.com/dragon1086/amp-assistant/actions)

**[Quickstart](#install)** · **[How it works](#how-it-works)** · **[Configuration](#configuration)** · **[MCP Server](#mcp-server)** · **[Docs](docs/)**

<br/>

**Read in:** [한국어](README.ko.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [Español](README.es.md)

</div>

---

## The problem with asking one AI

A single AI has blind spots. It was trained on the same data, carries the same biases, and optimizes for the response most likely to satisfy you — not the most accurate one.

**amp fixes this by running two independent AI agents in parallel, making them debate, and synthesizing the best answer from both.**

<div align="center">

![architecture diagram](docs/assets/architecture.png)

</div>

---

## Install

```bash
pip install amp-reasoning
```

**Option 1 — API keys** (fastest, <20s responses):
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
amp init
```

**Option 2 — Free with OAuth** (requires ChatGPT Plus + Claude Max subscriptions):
```bash
amp login    # browser OAuth, no API keys needed, cost = $0
```

**Option 3 — One-line installer:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## Demo

<div align="center">

![amp terminal demo](docs/assets/demo.svg)

</div>

---

## How It Works

amp uses a **Cross-agent Semantic Entropy Ratio (CSER)** to measure how differently two AIs approach the same question. The more independent their reasoning, the better the synthesis.

### Default — 2-round parallel analysis

```
Question ──┬──► Agent A (GPT-5)     ──► independent analysis
           └──► Agent B (Claude)    ──► independent analysis
                      │
                      ▼
               Reconciler synthesizes
                      │
                      ▼
          Answer + CSER score + agreements + conflicts
```

Agent A and B run **in parallel** and never see each other's work. This guarantees genuine independence and maximizes CSER.

### Emergent — 4-round structured debate

When you need to go deeper (or when CSER < 0.30, triggering the auto-upgrade):

```
Round 1 ── Agent A analyzes
Round 2 ── Agent B challenges A's reasoning
Round 3 ── Agent A rebuts B's challenge
Round 4 ── Agent B delivers final counterpoint
                    │
                    ▼
           Reconciler synthesizes all rounds
```

### Knowledge Graph

amp builds a local knowledge graph (`~/.amp/kg.db`) from every query. Over time, it accumulates context about your domain and improves synthesis quality.

---

## Configuration

```bash
amp init    # interactive setup wizard
```

`~/.amp/config.yaml`:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2              # gpt-5.2 · gpt-5.4 · gpt-5.4-mini
    reasoning_effort: high      # none · low · medium · high · xhigh

  agent_b:
    provider: anthropic         # or: anthropic_oauth (free, slower)
    model: claude-sonnet-4-6    # claude-opus-4-6 · claude-haiku-4-6

amp:
  parallel: true        # run A+B in parallel (default: true, ~50% faster)
  timeout: 90           # per-agent timeout in seconds
  kg_path: ~/.amp/kg.db
```

### Supported Providers

| Provider | Speed | Cost | Setup |
|----------|:-----:|------|-------|
| `openai` | ⚡⚡⚡ | ~$0.03–0.08/q | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **Free** | ChatGPT Plus + `amp login` |
| `anthropic` | ⚡⚡⚡ | ~$0.03–0.08/q | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **Free** | Claude Max + `amp login` |
| `gemini` | ⚡⚡⚡ | ~$0.01–0.04/q | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | ~$0.001/q | `DEEPSEEK_API_KEY` |
| `mistral` | ⚡⚡⚡ | ~$0.002/q | `MISTRAL_API_KEY` |
| `xai` | ⚡⚡⚡ | ~$0.02/q | `XAI_API_KEY` |
| `local` | ⚡⚡ | Free | Ollama running |

> **Tip:** Mix providers from different vendors for maximum diversity.
> `openai` × `anthropic` gives the highest CSER in practice.

---

## MCP Server

Works with **Claude Desktop**, **Cursor**, **Windsurf**, **OpenClaw**, and any
[MCP-compatible](https://modelcontextprotocol.io) client.

```bash
amp serve   # starts at http://127.0.0.1:3010
```

Add to your MCP config (`claude_desktop_config.json` or similar):
```json
{
  "mcpServers": {
    "amp": {
      "url": "http://127.0.0.1:3010"
    }
  }
}
```

Available tools:

| Tool | What it does | Typical time |
|------|-------------|:------------:|
| `analyze` | 2-round parallel analysis | 15–30s |
| `debate` | 4-round structured debate | 30–60s |
| `quick_answer` | single-model fast answer | ~3s |

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

print(result["answer"])           # synthesized final answer
print(f"CSER: {result['cser']:.2f}")          # 0–1, how different the AIs were
print(f"Agreements: {result['agreements']}")  # what both AIs agreed on
print(f"Conflicts:  {result['conflicts']}")   # where they disagreed
```

---

## Docker

```bash
# MCP server in Docker
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

# docker-compose
OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## Performance

Benchmarks on Apple M-series, 2026-03, parallel mode:

| Setup | p50 latency | p95 latency | Cost/query |
|-------|:-----------:|:-----------:|:----------:|
| GPT-5.2 × Claude Sonnet (API) | 18s | 28s | $0.03–0.08 |
| GPT-5.2 × Claude OAuth | 32s | 48s | ~$0.01 |
| GPT-5.2 × DeepSeek V3 | 15s | 22s | ~$0.005 |
| GPT-5.2 × GPT-5.2 (same vendor) | 15s | 20s | $0.02–0.05 |

Parallel A+B execution delivers **~50% speedup** vs sequential (v0.1.0+).

---

## Why cross-vendor synthesis works

GPT and Claude were trained by different organizations, on different corpora, with different alignment techniques. They disagree more often — and more meaningfully — than two instances of the same model.

Same-vendor pairs (e.g., GPT+GPT) also work: amp automatically assigns extreme opposite personas to each agent to maximize diversity. But cross-vendor naturally produces higher CSER.

---

## Contributing

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

Open an issue before large PRs. All contributions welcome.

---

## License

MIT © 2026 amp contributors
