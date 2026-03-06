<div align="center">

![amp banner](docs/assets/banner.png)

<h3>Two AIs argue. You get a better answer.</h3>

[![PyPI version](https://img.shields.io/pypi/v/amp-reasoning?color=7c3aed&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Downloads](https://img.shields.io/pypi/dm/amp-reasoning?color=0891b2&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/dragon1086/amp-assistant/test.yml?style=flat-square&label=CI)](https://github.com/dragon1086/amp-assistant/actions)

**[Why amp?](#why-amp-not-just-two-api-calls)** · **[Install](#install)** · **[How it works](#how-it-works)** · **[Benchmark](#benchmark)** · **[Config](#configuration)**

<br/>

**Read in:** [한국어](README.ko.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [Español](README.es.md)

</div>

---

## Why amp? Not just two API calls.

"Just call two LLMs and merge the outputs" sounds equivalent. It isn't. Here's why:

### Problem 1 — Sequential debate creates anchoring bias

Most multi-agent systems work like this:

```
Agent A answers → Agent B reads A's answer → Agent B responds
```

The moment Agent B reads Agent A's output, it anchors on A's framing. B's "critique" converges toward A's structure, vocabulary, and assumptions — even when disagreeing. The result looks like debate; it reasons like one mind.

**amp's solution — the independence invariant:** In 2-round mode, Agent A and Agent B run in parallel and *never* see each other's output. Independence is enforced architecturally, not by prompt instruction.

```
Question ──┬──► Agent A  [isolated]  ──► analysis A
           └──► Agent B  [isolated]  ──► analysis B
                          │
                          ▼
                   Reconciler synthesizes
                   (first time either output is seen together)
```

### Problem 2 — Same-vendor models aren't truly independent

GPT-4 + GPT-4 with different prompts will produce high lexical overlap. The training data, RLHF alignment, and prior distribution are shared — diversity is mostly surface-level.

**amp's solution — same-vendor divergence engine:** amp automatically detects whether both agents use the same vendor. If they do, it assigns extreme domain-specific opposing personas and different temperatures:

| Domain | Agent A persona | Agent B persona | Temps |
|--------|----------------|-----------------|-------|
| `investment` | Quant risk analyst — downside protection, stats | Momentum growth investor — asymmetric bets, trends | 0.3 / 1.1 |
| `business` | Risk-managing CFO — cash flow, conservative growth | Visionary founder — market disruption, 10× growth | 0.3 / 1.1 |
| `career` | Career optimization strategist — data-driven, risk-min | Disruptive coach — nonlinear leaps, reject comfort | 0.3 / 1.1 |
| `ethics` | Deontological ethicist — principle-based, absolute | Utilitarian pragmatist — outcome-driven, contextual | 0.3 / 1.1 |

9 domains in total. Cross-vendor pairs (GPT × Claude) skip this — their divergence is structural.

### Problem 3 — "Better answer" is unverifiable without measurement

How do you know the synthesis was actually better than either agent alone? Without a metric, you're guessing.

**amp's solution — CSER (Cognitive Synthesis Emergence Rate):**

```
CSER = (unique_insights_A + unique_insights_B) / total_insights
```

CSER measures what fraction of the total insight pool was *unique* to each agent — i.e., not shared. CSER = 1.0 means every insight came from only one agent (maximum divergence). CSER = 0.0 means both agents said the same things (echo chamber).

- **CSER ≥ 0.30** → synthesis proceeds (θ threshold, from empirical calibration)
- **CSER < 0.30** → amp automatically escalates to 4-round debate to force more divergence

This is the gate. Without it, you'd never know if you're getting emergence or an expensive echo chamber.

### Problem 4 — OpenAI and Anthropic cannot build this

Cross-vendor synthesis — GPT analyzing against Claude — is the product's core mechanism. OpenAI won't ship a feature that credits Anthropic. Anthropic won't ship one that credits OpenAI. Only a neutral, open-source project can put both on equal footing and let them genuinely compete.

This isn't an incidental feature. It's why amp has to exist as open source.

---

## How It Works

<div align="center">

![architecture](docs/assets/architecture.png)

</div>

### 2-round — parallel independent analysis (default)

1. **Auto-persona:** amp detects the query domain (9 categories, LLM fallback) and assigns contrasting expert personas to each agent.
2. **Parallel execution:** Agent A and B run simultaneously with no cross-visibility.
3. **CSER measurement:** unique and shared insights are computed via Jaccard similarity on extracted idea units.
4. **Gate:** if CSER < θ, auto-escalate to 4-round.
5. **Reconcile + Verify:** a third LLM call synthesizes agreements, conflicts, and a final answer.
6. **KG update:** the question, synthesis, and CSER score are stored in a local knowledge graph with a weighted edge (`PRODUCES`, weight = CSER).

### 4-round — structured debate (emergent mode)

```
Round 1 ── Agent A analyzes
Round 2 ── Agent B challenges A's reasoning     (A's output now visible to B)
Round 3 ── Agent A rebuts B's challenge
Round 4 ── Agent B delivers final counterpoint
                    │
                    ▼
           Reconciler synthesizes all rounds
```

### Knowledge Graph — synthesis that improves over time

The KG (`~/.amp/kg.db`) is not a static knowledge base. Every synthesis is stored as a node with its CSER score. The edge weight from question→synthesis is CSER itself:

```python
kg.relate(question_id, synthesis_id, "PRODUCES", weight=cser)
```

When you ask a related question later, amp retrieves semantically similar past syntheses (OpenAI embeddings + cosine similarity) and injects them as context. The KG is a **growing domain intelligence layer** — amp gets more accurate in your specific domain the more you use it.

---

## Benchmark

Blind A/B evaluation: amp ON vs single GPT-5.2. Gemini used as judge with randomized labels (no model identity disclosed). N=30 questions across 7 domains.

| Domain | amp wins | Solo wins | amp win rate |
|--------|:--------:|:---------:|:------------:|
| resource_allocation | 4 | 1 | **80%** |
| strategy | 4 | 2 | **67%** |
| emotion | 3 | 2 | 60% |
| career | 0 | 3 | 0% |
| relationship | 1 | 4 | 20% |
| ethics | 1 | 4 | 20% |
| **Overall (N=30)** | **13** | **17** | **43%** |

**Honest interpretation:** amp is not universally better. It outperforms significantly on open-ended, multi-perspective problems (strategy, resource allocation). For factual career and relationship advice, a single expert model is often sufficient. Use `amp quick` when you want a fast expert answer. Use `amp` when the question genuinely has multiple valid framings.

---

## Demo

<div align="center">

![amp terminal demo](docs/assets/demo.svg)

*Illustrative output. Actual CSER and timing vary by query and provider.*

</div>

---

## Install

```bash
pip install amp-reasoning
```

**Option 1 — API keys** (fastest, ~15–25s responses):
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
amp init
```

**Option 2 — Free with OAuth** (requires ChatGPT Plus + Claude Max subscriptions):
```bash
amp login    # browser OAuth, no API keys needed, cost ≈ $0
```

**Option 3 — One-line installer:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## Quick Start

```bash
# Emergent analysis (parallel A+B + CSER + synthesis)
amp "Should I raise a Series A now or extend runway?"
amp "React vs Vue for a new project in 2026 — with a team of 4"
amp "What are the real risks of this contract clause?"

# Fast single-model answer (no debate)
amp -m solo "What is the current Fed funds rate?"

# 4-round structured debate
amp -m emergent "Will AGI arrive before 2028?"

# MCP server for Claude Desktop / Cursor / OpenClaw
amp serve
```

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
  parallel: true        # run A+B in parallel (~50% faster vs sequential)
  timeout: 90           # per-agent timeout in seconds
  kg_path: ~/.amp/kg.db
  kg_search_timeout: 2  # KG semantic search timeout (seconds)
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

> **Highest CSER in practice:** `openai` × `anthropic` — trained by different organizations on different corpora with different alignment methods. Structural divergence, not prompted divergence.

---

## MCP Server

Works with **Claude Desktop**, **Cursor**, **Windsurf**, **OpenClaw**, and any [MCP-compatible](https://modelcontextprotocol.io) client.

```bash
amp serve   # starts at http://127.0.0.1:3010
```

`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "amp": { "url": "http://127.0.0.1:3010" }
  }
}
```

| Tool | Description | Latency |
|------|-------------|:-------:|
| `analyze` | parallel 2-round + CSER gate | 15–30s |
| `debate` | 4-round structured debate | 30–60s |
| `quick_answer` | single-model fast answer | ~3s |

---

## Python API

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(
    query="Should we pivot to enterprise or double down on consumer?",
    context=[],
    config=config,
)

print(result["answer"])
print(f"CSER: {result['cser']:.2f}")          # 0 = echo chamber, 1 = max divergence
print(f"Agreements: {result['agreements']}")  # what both AIs agreed on
print(f"Conflicts:  {result['conflicts']}")   # where they genuinely differed
print(f"Gate triggered: {result['cser_gate_triggered']}")
```

---

## Docker

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## When to use amp

| Question type | Recommended | Why |
|--------------|-------------|-----|
| "Should I raise now or extend runway?" | `amp` | Multiple valid framings, high stakes |
| "React vs Vue for 2026?" | `amp` | No single right answer; depends on factors |
| "What's the capital of France?" | `amp -m solo` | Single correct answer; debate is waste |
| "Review this contract clause" | `amp` | Adversarial stress-testing has high value |
| "Summarize this document" | `amp -m solo` | Retrieval task; no emergence benefit |
| "What are the risks of this strategy?" | `amp` | Blind spots benefit from two perspectives |

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
