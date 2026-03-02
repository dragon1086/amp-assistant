# amp

**Two minds. One answer.**

amp is a local, open-source, privacy-first personal assistant powered by **emergent 2-agent collaboration**. Two AI agents independently analyze every complex query, then reconcile — producing richer, more reliable answers than any single-agent system.

All your data stays on your machine. No cloud sync. No telemetry.

---

## Why emergent collaboration?

Most AI assistants use a single model call. amp uses three modes, automatically selected:

| Mode | When | How |
|------|------|-----|
| **Solo** | Simple facts, greetings | 1 LLM call — fast and cheap |
| **Pipeline** | Code, documents, step-by-step | Plan → Solve → Review → Fix |
| **Emergent** | Analysis, decisions, reviews | A proposes → B attacks → Reconcile → Verify |

The emergent mode is the killer feature. Here's what it catches:

```
> 이 마케팅 문구 어때? "우리 제품은 경쟁사보다 10배 빠릅니다"

Solo mode answer:
  "강력한 주장이네요! 효과적인 마케팅 문구입니다."

Emergent mode:
  [Agent A — Analyst]
  강조 효과는 충분하지만 구체적인 벤치마크 데이터가 없으면
  소비자 신뢰를 얻기 어렵습니다.

  [Agent B — Critic]
  "10배"라는 수치는 측정 기준이 불명확합니다. 어떤 조건에서의
  10배인지 명시하지 않으면 법적 리스크가 될 수 있습니다.

  ━━━━━━━━━━━━━━━━━━━━
  ✅ 결론: 주장을 뒷받침할 구체적인 벤치마크 수치와 측정 조건을
  명시하세요. "특정 조건 X에서 평균 10배 빠름 (벤치마크 참조)" 형식
  으로 수정하면 설득력과 법적 안전성이 모두 높아집니다.
  📊 신뢰도: CSER 0.71 ✅ (높음)
  ━━━━━━━━━━━━━━━━━━━━
```

**CSER** (Cognitive Synthesis Emergence Rate) measures how much unique insight each agent contributed. High CSER = healthy divergent thinking. Low CSER = echo chamber.

---

## Quick install

```bash
pip install amp-assistant
amp setup          # interactive setup (API key, model, etc.)
amp "hello"        # test it works
```

Or from source:

```bash
git clone https://github.com/amp-assistant/amp
cd amp
pip install -e .
export OPENAI_API_KEY=sk-...
amp "hello"
```

---

## Usage

### Single query

```bash
amp "내일 있을 투자자 미팅 준비 어떻게 해야 할까?"
amp --mode emergent "이 계획의 문제점이 뭘까?"
amp --mode pipeline "Python으로 CSV 파일 정렬하는 코드 짜줘"
amp --mode solo "파이썬 현재 버전이 뭐야?"
```

### Interactive REPL

```bash
amp

> 안녕!
amp (solo): 안녕하세요! 무엇을 도와드릴까요?

> 이 문장 검토해줘: "우리 제품은 경쟁사보다 10배 빠릅니다"
[Emergent mode auto-selected]
...

> /stats
KG: 3 nodes, 1 edges | Sessions: 2 | CSER avg: 0.65

> /mode pipeline     # force pipeline mode
> /clear             # clear conversation history
> /help              # show all commands
```

---

## Configuration

amp reads `~/.amp/config.yaml`:

```yaml
llm:
  provider: openai        # or anthropic
  model: gpt-4o-mini      # default (cheap + fast)
  api_key: ${OPENAI_API_KEY}

telegram:
  token: ${TELEGRAM_BOT_TOKEN}

amp:
  default_mode: auto      # auto | solo | pipeline | emergent
  kg_path: ~/.amp/kg.json
```

Run `amp setup` for interactive configuration.

**Supported models:**
- OpenAI: `gpt-4o-mini` (default), `gpt-4o`, `gpt-4.1`
- Anthropic: `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`

---

## Knowledge Graph

Every emergent analysis is automatically saved to a local JSON knowledge graph at `~/.amp/kg.json`. amp builds a personal memory of your decisions and insights over time — all local, all yours.

---

## Telegram Bot

1. Create a bot via [@BotFather](https://t.me/botfather) and get your token
2. Add to config or set env var:
   ```bash
   export TELEGRAM_BOT_TOKEN=your-token-here
   ```
3. Start the bot:
   ```bash
   python -m amp.interfaces.telegram_bot
   ```

Bot commands: `/start`, `/mode`, `/stats`, `/clear`

---

## Architecture

```
query
  │
  ▼
router.py ──────────────────────────────────┐
  │ (keyword + length heuristics)           │
  │                                         │
  ├─ solo ──────────────────────────────────┤
  │   └─ 1 LLM call                        │
  │                                         │
  ├─ pipeline ──────────────────────────────┤
  │   └─ plan → solve → review → fix       │
  │      (4 sequential LLM calls)          │
  │                                         │
  └─ emergent ─────────────────────────────┘
      ├─ Agent A (analyst)  ─┐ parallel, independent
      ├─ Agent B (critic)   ─┘
      ├─ Reconciler (sees both → synthesize)
      └─ Verifier (logical consistency check)
           │
           └─ auto-save to KG
```

---

## Contributing

amp is built on the idea that **cognitive diversity produces better answers**. The emergent engine is inspired by research in ensemble methods, adversarial collaboration, and multi-agent debate ([Du et al., 2023](https://arxiv.org/abs/2305.14325); [Liang et al., 2023](https://arxiv.org/abs/2305.19118)).

Contributions welcome:
- New routing heuristics
- Additional LLM provider adapters
- Alternative emergent synthesis strategies
- Evaluation benchmarks for CSER

```bash
pip install -e ".[dev]"
pytest tests/
```

---

## License

MIT — use it however you want.
