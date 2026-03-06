# amp Architecture

Technical reference for contributors, researchers, and enterprise evaluators.

**Table of Contents**

1. [System Overview](#system-overview)
2. [Agent Isolation Invariant](#agent-isolation-invariant)
3. [CSER — Cognitive Synthesis Emergence Rate](#cser--cognitive-synthesis-emergence-rate)
4. [Execution Modes](#execution-modes)
5. [Auto-Persona Engine](#auto-persona-engine)
6. [Dynamic Domain Registry](#dynamic-domain-registry)
7. [Knowledge Graph](#knowledge-graph)
8. [LLM Factory](#llm-factory)
9. [MCP Server](#mcp-server)
10. [Performance Characteristics](#performance-characteristics)
11. [Academic References](#academic-references)

---

## System Overview

```
User query
    │
    ▼
┌───────────────────────────────────────────────────────┐
│  Auto-Persona Engine                                  │
│  ┌────────────────────────────────────────────────┐  │
│  │ 1. Static keyword match (9 built-in presets)   │  │
│  │ 2. DomainRegistry.find()  (embedding cache)    │  │
│  │ 3. DomainRegistry.create() (LLM + persist)     │  │
│  └────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
    │ persona_a, persona_b
    ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│  Agent A                │  │  Agent B                │
│  (e.g. GPT-5.2)         │  │  (e.g. Claude Sonnet)   │
│  persona_a              │  │  persona_b              │
│  ISOLATED — no cross-   │  │  ISOLATED — no cross-   │
│  visibility in 2-round  │  │  visibility in 2-round  │
└─────────────────────────┘  └─────────────────────────┘
    │ response_a                   │ response_b
    └──────────────┬───────────────┘
                   ▼
          CSER Measurement
          ┌───────────────────────────────┐
          │ Jaccard on extracted ideas    │
          │ CSER = (|A-B| + |B-A|)/|A∪B| │
          │ θ = 0.30 gate               │
          └───────────────────────────────┘
               │              │
          CSER ≥ 0.30     CSER < 0.30
               │              │
               ▼              ▼
          Reconciler    Escalate to
          (3rd call)    4-round debate
               │
               ▼
          Final synthesis
          + KG update (CSER-weighted edge)
```

---

## Agent Isolation Invariant

### The Problem

Most multi-agent systems pass one agent's output as input to the next:

```
Agent A → output_A → Agent B reads output_A → responds
```

This creates **anchoring bias**: Agent B, having read Agent A's framing, vocabulary, and conclusions, tends to respond within A's conceptual frame — even when formally disagreeing. The result looks like debate but reasons like one mind.

### amp's Solution

In 2-round mode, agents run in parallel with **zero cross-visibility**:

```python
# emergent.py — core isolation implementation
with ThreadPoolExecutor(max_workers=2) as executor:
    future_a = executor.submit(_call_agent, agent_a_config, prompt_a)
    future_b = executor.submit(_call_agent, agent_b_config, prompt_b)
    response_a = future_a.result(timeout=AGENT_TIMEOUT)
    response_b = future_b.result(timeout=AGENT_TIMEOUT)
# Neither agent sees the other's output during generation.
# First cross-visibility happens at Reconciler.
```

**Why this matters:** Independence is an architectural guarantee, not a prompt instruction. "Don't look at the other agent's answer" in a system prompt can be overridden. Parallel execution with no shared context cannot.

### 4-Round Mode

When CSER falls below θ=0.30, amp escalates to structured adversarial debate. Here, agents *do* see each other's outputs sequentially — the isolation invariant is intentionally relaxed to force genuine challenge:

```
Round 1: Agent A analyzes in isolation
Round 2: Agent B reads A's output, challenges it
Round 3: Agent A reads B's challenge, rebuts
Round 4: Agent B delivers final counterpoint
```

Reconciler synthesizes all four rounds. CSER is re-measured on rounds 1 and 4 to quantify whether the debate produced new insights.

---

## CSER — Cognitive Synthesis Emergence Rate

### Definition

CSER measures the fraction of total insights that were **unique** to each agent — not present in the other's response. It is the operational definition of "did two minds actually think differently?"

```
CSER = (|unique_A| + |unique_B|) / |total_insights|

Where:
  unique_A  = ideas in A's response not present in B's
  unique_B  = ideas in B's response not present in A's
  total     = A ∪ B (all unique ideas across both responses)
```

Range: `[0.0, 1.0]`
- `CSER = 1.0` — every insight was unique to one agent (maximum divergence, maximum emergence potential)
- `CSER = 0.0` — both agents said identical things (echo chamber, synthesis adds no value)
- `θ = 0.30` — empirically calibrated gate threshold (from internal benchmark on 30 questions)

### Implementation

```python
# amp/core/metrics.py
def compute_cser(response_a: str, response_b: str) -> float:
    ideas_a = _extract_ideas(response_a)   # sentence-level split + normalize
    ideas_b = _extract_ideas(response_b)

    if not ideas_a or not ideas_b:
        return 0.5  # fallback

    unique_a = ideas_a - ideas_b
    unique_b = ideas_b - ideas_a
    total    = ideas_a | ideas_b

    return (len(unique_a) + len(unique_b)) / len(total)


def _extract_ideas(text: str) -> set[str]:
    # Split on sentence boundaries, normalize whitespace, deduplicate
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return {s.strip().lower() for s in sentences if len(s.strip()) > 20}
```

### Gate Logic (`amp/core/cser_gate.py`)

```python
CSER_GATE_THRESHOLD = 0.30

def should_retry(cser, current_rounds, retry_count):
    if cser >= CSER_GATE_THRESHOLD:
        return False, current_rounds, "pass"
    if current_rounds == 2:
        return True, 4, "upgrade_to_4round"   # escalate
    return False, current_rounds, "low_cser_flagged"  # give up with warning
```

### Benchmark Calibration

θ=0.30 was selected based on internal A/B evaluation (N=30, Gemini blind judge):
- CSER > 0.30 correlated with amp winning vs solo GPT-5.2 in strategy and resource allocation domains
- CSER < 0.30 correlated with amp performing at or below solo baseline
- θ=0.30 is conservative: it allows synthesis even when ideas overlap 70%, which handles naturally verbose but substantively distinct responses

---

## Execution Modes

| Mode | Rounds | Agent visibility | Use case |
|------|--------|-----------------|---------|
| `auto` | 2 or 4 | Isolated (2R) / sequential (4R) | Default: CSER decides |
| `solo` | 1 | N/A (single agent) | Fast factual queries |
| `pipeline` | 2 | Isolated | Always 2-round, never escalates |
| `emergent` | 4 | Sequential | Force structured debate |

**2-round parallel execution is ~50% faster** than sequential: both agents run simultaneously via `ThreadPoolExecutor(max_workers=2)`. Total latency ≈ max(agent_a_latency, agent_b_latency) + reconciler_latency.

---

## Auto-Persona Engine

### Purpose

Contrasting personas are the primary mechanism for inducing cognitive diversity between agents. Without them, even cross-vendor agents tend to converge on similar framings for common questions.

### Domain Detection (3-stage)

```
Stage 1: Static keyword matching (O(1))
  ─ 9 built-in preset domains: career, relationship, business, investment,
    legal_contract, health, ethics, creative, parenting
  ─ Keyword lists in DOMAIN_KEYWORDS dict
  ─ ~70% of real-world queries resolved here

Stage 2: DomainRegistry.find() — cosine similarity lookup
  ─ Embeds query with text-embedding-3-small
  ─ Compares against stored domain embeddings in SQLite
  ─ Returns cached domain if similarity ≥ REUSE_THRESHOLD (0.78)
  ─ ~20% of queries (previously unknown, now cached)

Stage 3: DomainRegistry.create() — LLM domain creation
  ─ gpt-5-mini generates: domain_name, keywords, persona_a/b, sv_persona_a/b
  ─ Dedup merge check: if new domain embedding ≥ MERGE_THRESHOLD (0.75) to
    existing domain → merge (return existing) instead of creating duplicate
  ─ Otherwise: save new domain to DB for future reuse
  ─ ~10% of queries (genuinely novel domains)
```

### Same-Vendor Detection

If both agents share a vendor (e.g., GPT-5 + GPT-5), their RLHF alignment and training data distribution are shared. Standard contrasting personas are insufficient — the underlying model will "pull" both agents toward similar conclusions regardless of persona framing.

**Solution: `SAME_VENDOR_PRESETS` + temperature splitting**

```python
SAME_VENDOR_TEMPS = (0.3, 1.1)  # agent_a: conservative, agent_b: exploratory

# Example: investment domain, same-vendor mode
persona_a = "퀀트 리스크 애널리스트 — 하방 보호, 포트폴리오 헤징, 통계 근거"
persona_b = "모멘텀 성장 투자자 — 비대칭 수익, 집중 배팅, 추세 추종"
# Extreme archetypes + orthogonal temperatures
# forces behavioral divergence even with shared priors
```

Cross-vendor pairs (GPT × Claude) skip this — their structural divergence (different training, different RLHF, different value alignment) is sufficient.

---

## Dynamic Domain Registry

### Motivation

The 9 built-in preset domains cover ~70% of real queries. The remaining 30% now go through the dynamic registry — meaning the total domain pool is **unbounded** and grows with every novel query type.

### Architecture

```python
# amp/core/domain_registry.py

class DomainRegistry:
    """SQLite-backed dynamic domain pool."""

    # Schema (domains table in ~/.amp/kg.db):
    # id, name (UNIQUE), keywords (JSON), persona_a, persona_b,
    # sv_persona_a, sv_persona_b, embedding (JSON), usage_count, created_at

    REUSE_THRESHOLD  = 0.78   # cosine: reuse existing domain
    MERGE_THRESHOLD  = 0.75   # cosine: merge new into existing (dedup)
```

### Creation Flow

```
Unknown query
    │
    ▼ gpt-5-mini (1 call)
{
  "name": "dna_forensics_ethics",
  "keywords": ["DNA 증거", "기소 판단", ...],
  "persona_a": "법의학 전문가 겸 형사법 자문 — 증거 신뢰성, 통계 해석",
  "persona_b": "형사 방어 변호사 — 무죄 추정, 절차적 공정성",
  "sv_persona_a": "...(extreme version for same-vendor mode)",
  "sv_persona_b": "..."
}
    │
    ▼ Embed domain description
    │
    ├─ Merge check (≥0.75 to existing) → reuse existing
    │
    └─ Save to DB → future queries via embedding lookup
```

### Growth Behavior

The domain pool grows monotonically with novel query types. `amp domains` shows the current registry:

```bash
$ amp domains
🧠 동적 도메인 레지스트리 (3개 학습됨)

  [dna_forensics_ethics]
    키워드: DNA 증거, 기소 판단, 합리적 의심, 증거 신뢰성
    사용횟수: 5

  [urban_planning_green_vs_housing]
    키워드: 도심 녹지, 주거 공급, 도시 정책, 우선순위
    사용횟수: 2
```

---

## Knowledge Graph

### Schema

```sql
-- nodes: questions, syntheses, insights
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT DEFAULT 'insight',   -- 'question' | 'synthesis' | 'insight'
    content     TEXT NOT NULL,
    tags        TEXT DEFAULT '[]',        -- JSON array
    metadata    TEXT DEFAULT '{}',        -- JSON object
    embedding   TEXT DEFAULT NULL,        -- JSON array (1536-dim float)
    created_at  TEXT NOT NULL
);

-- edges: directional relationships with CSER-weighted strength
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES nodes(id),
    target_id   TEXT NOT NULL REFERENCES nodes(id),
    relation    TEXT NOT NULL,            -- e.g. 'PRODUCES', 'RELATED_TO'
    weight      REAL DEFAULT 1.0,         -- CSER score for PRODUCES edges
    created_at  TEXT NOT NULL
);

-- dynamic domain registry (same DB file)
CREATE TABLE domains (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    keywords     TEXT DEFAULT '[]',
    persona_a    TEXT NOT NULL,
    persona_b    TEXT NOT NULL,
    sv_persona_a TEXT NOT NULL,
    sv_persona_b TEXT NOT NULL,
    embedding    TEXT,
    usage_count  INTEGER DEFAULT 0,
    created_at   REAL DEFAULT (unixepoch())
);
```

### Semantic Search

```python
def search(self, query: str, top_k: int = 3, node_type: str = None) -> list[dict]:
    query_emb = np.array(self.embedder.embed(query))

    # Load all nodes with embeddings (flat scan)
    rows = self.conn.execute(
        "SELECT id, content, embedding FROM nodes WHERE embedding IS NOT NULL"
    ).fetchall()

    # Cosine similarity: numpy vectorized
    scored = []
    for row in rows:
        node_emb = np.array(json.loads(row["embedding"]))
        cos = float(np.dot(query_emb, node_emb) /
                    (np.linalg.norm(query_emb) * np.linalg.norm(node_emb)))
        scored.append((cos, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in scored[:top_k]]
```

### Scalability

| Node count | Flat search latency | Action required |
|-----------|--------------------|----|
| < 10K     | < 10ms             | None |
| 10K–100K  | 50–500ms           | Add `kg_search_timeout` in config (default: 2s) |
| > 100K    | > 500ms            | Swap to FAISS IVF index (adapter pattern, no KG logic change) |

The `EmbeddingAdapter` pattern allows dropping in FAISS, ChromaDB, or a local model without changing KG or emergent logic:

```python
class EmbeddingAdapter:
    """Provider-agnostic embedding interface."""
    def embed(self, text: str) -> list[float]: ...

# Future: local model, no API cost
class LocalEmbeddingAdapter(EmbeddingAdapter):
    def embed(self, text: str) -> list[float]:
        return sentence_transformer.encode(text).tolist()
```

### KG Update Flow

After every successful synthesis:

```python
# 1. Store question node
q_id = kg.add(query, node_type="question", tags=[domain])

# 2. Store synthesis node
s_id = kg.add(synthesis_text, node_type="synthesis",
              metadata={"cser": cser_score, "mode": mode})

# 3. Connect with CSER-weighted edge
kg.relate(q_id, s_id, "PRODUCES", weight=cser_score)
```

High-CSER syntheses get higher edge weights, making them more likely to surface as context in future related queries. The KG is a **naturally self-curating** memory: better reasoning sessions leave stronger traces.

---

## LLM Factory

### Provider Support

| Provider | ID in config | Auth |
|----------|-------------|------|
| OpenAI GPT-5.x | `openai` | `OPENAI_API_KEY` |
| OpenAI (free) | `openai_oauth` | Codex CLI OAuth |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Anthropic (free) | `anthropic_oauth` | `claude` CLI OAuth |
| Google Gemini | `gemini` | `GEMINI_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |
| xAI Grok | `xai` | `XAI_API_KEY` |
| Local (Ollama) | `local` | None |

### OAuth Path (Claude)

When `anthropic_oauth` is configured, amp calls the `claude` CLI subprocess:

```python
result = subprocess.run(
    ["claude", "-p", "--output-format", "json", prompt],
    capture_output=True, text=True, timeout=120
)
```

This uses the user's Claude Max subscription (cost ≈ $0). The subprocess path adds ~20–30s latency vs direct API. If `ANTHROPIC_API_KEY` is set, amp uses the direct API path automatically (< 5s).

### Timeout Configuration

```python
AGENT_TIMEOUT   = 90   # per-agent wall-clock (seconds)
RECONCILE_TIMEOUT = 30  # reconciler call
MCP_OUTER_TIMEOUT = 180  # full MCP request budget
```

---

## MCP Server

amp exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `http://127.0.0.1:3010`.

### Tools

| Tool | Description |
|------|-------------|
| `analyze` | Full emergent analysis (2-agent + CSER + synthesis) |
| `quick_answer` | Solo mode — single LLM, fast |
| `kg_search` | Semantic search over past syntheses |
| `cser_score` | Compute CSER between two texts |

### Transport

Supports both **Streamable HTTP** (MCP 2025 spec) and **SSE** (legacy). Client compatibility:
- Claude Desktop (SSE)
- Cursor / Windsurf (Streamable HTTP)
- OpenClaw (Streamable HTTP)
- Any MCP-compatible client

### Auto-start (macOS)

```bash
# Register with launchd (survives reboots + crash recovery)
amp serve --install-launchd
# or manually:
launchctl load ~/Library/LaunchAgents/ai.amp.mcp-server.plist
```

---

## Performance Characteristics

### Typical Latency Breakdown

| Stage | OpenAI API | Claude OAuth |
|-------|-----------|-------------|
| Domain detection (keyword) | ~0ms | ~0ms |
| Domain detection (registry) | ~300ms | ~300ms |
| Domain detection (LLM create) | ~3–5s | ~3–5s |
| Agent A+B (parallel) | ~5–15s | ~20–30s |
| CSER computation | ~10ms | ~10ms |
| Reconciler | ~3–8s | ~3–8s |
| KG search + update | ~200–500ms | ~200–500ms |
| **Total (2-round)** | **~10–25s** | **~25–40s** |

### Cost per Query (approximate, 2026-03 pricing)

| Configuration | Cost/query |
|--------------|-----------|
| GPT-5.2 × 2 (both agents) | ~$0.06–0.12 |
| GPT-5.2 + Claude Sonnet | ~$0.04–0.08 |
| GPT-5-mini × 2 | ~$0.003–0.008 |
| Claude OAuth + GPT OAuth | **$0.00** |
| DeepSeek V3 × 2 | ~$0.001–0.003 |

---

## Academic References

| Reference | Relevance to amp |
|-----------|----------------|
| Du, Y. et al. *Improving Factuality and Reasoning in Language Models through Multiagent Debate*. ICML 2024. ([arXiv:2305.14325](https://arxiv.org/abs/2305.14325)) | Foundation for multi-agent debate; amp extends to open-ended advisory tasks |
| Zeng, et al. *ECON: From Debate to Equilibrium — Belief-Driven Multi-Agent LLM Reasoning via Bayesian Nash Equilibrium*. ICML 2025. ([GitHub](https://github.com/tmlr-group/ECON)) | Theoretical grounding for agent coordination; amp uses empirical CSER instead of Bayesian equilibrium |
| Smit, A. et al. *Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs*. InstaDeep 2024. ([arXiv:2311.17371](https://arxiv.org/abs/2311.17371)) | Shows no single debate strategy dominates; amp's adaptive 2→4 round mechanism addresses this |
| Du, Y. et al. *Multi-LLM Debate: Framework, Principals, and Interventions*. OpenReview 2024. | Theoretical framework for multi-LLM debate principles; amp's independence invariant formalizes "principal diversity" |
| Topoteretes. *Cognee: Knowledge Engine for AI Agent Memory*. ([GitHub](https://github.com/topoteretes/cognee)) | KG-as-memory pattern; amp uses CSER-weighted edges (novel) vs standard knowledge graphs |
| Zep. *Graphiti: Build Real-Time Knowledge Graphs for AI Agents*. ([GitHub](https://github.com/getzep/graphiti)) | Temporal KG for agents; amp's KG is session-persistent rather than real-time streaming |

### Novel Contributions (not in prior literature)

1. **CSER metric** — domain-agnostic emergence measurement for open-ended synthesis quality
2. **Same-vendor divergence compensation** — detecting shared priors and applying extreme persona + temperature splitting
3. **Agent independence as architectural invariant** — enforced via parallel execution, not prompt instruction
4. **Dynamic domain registry** — KG-backed infinite domain pool that grows with usage
5. **CSER-weighted KG edges** — self-curating memory where higher-emergence syntheses surface preferentially

---

*Last updated: 2026-03. For implementation questions, open an issue on [GitHub](https://github.com/dragon1086/amp-assistant).*
