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

**한 줄 설치 (권장):**
```bash
curl -fsSL https://raw.githubusercontent.com/amp-assistant/amp/main/install.sh | bash
```
> pipx, uv, pip 순으로 자동 감지해서 설치합니다.

**pipx로 직접:**
```bash
pipx install git+https://github.com/amp-assistant/amp
amp setup   # 대화형 설정 wizard (API 키, 모델, 텔레그램 토큰)
amp "hello"
```

**uv로 (가장 빠름):**
```bash
uv tool install git+https://github.com/amp-assistant/amp
amp setup && amp "hello"
```

**PyPI (릴리스 버전):**
```bash
pip install amp-assistant
amp setup && amp "hello"
```

**소스에서:**
```bash
git clone https://github.com/amp-assistant/amp
cd amp && pip install -e .
amp setup
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

### 1. BotFather에서 토큰 발급

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색 → 대화 시작
2. `/newbot` 입력 → 봇 이름(표시명) 입력 → 봇 사용자명 입력 (`_bot` 으로 끝나야 함)
3. BotFather가 `123456789:ABCdef...` 형태의 API 토큰을 발급해줌

### 2. 토큰 설정

**방법 A — 환경변수 (권장)**
```bash
export TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

`.bashrc` / `.zshrc`에 추가하면 영구 적용됩니다.

**방법 B — .env 파일**
```bash
# ~/.amp/.env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

**방법 C — amp setup 마법사**
```bash
amp setup   # Step 3에서 텔레그램 토큰 입력
```

### 3. 봇 시작

```bash
bash start_bot.sh
```

또는 직접 실행:
```bash
python -m amp.interfaces.telegram_bot
```

### 봇 커맨드

| 커맨드 | 설명 |
|--------|------|
| `/start` | 시작 메시지 및 명령어 안내 |
| `/mode` | 현재 모드 확인 / 변경 (`auto`\|`solo`\|`pipeline`\|`emergent`) |
| `/model` | Agent A/B LLM 모델 확인 / 변경 |
| `/plugins` | 플러그인 목록 및 활성화 상태 |
| `/plugin on <이름>` | 플러그인 활성화 |
| `/plugin off <이름>` | 플러그인 비활성화 |
| `/imagine <프롬프트>` | 이미지 생성 (image_gen 플러그인 필요) |
| `/stats` | KG 통계 |
| `/clear` | 대화 기록 초기화 |

### 예시

```
/mode emergent
이 아키텍처 설계의 문제점이 뭘까?

/plugin on image_vision
[사진 전송]  → 이미지 분석

/imagine 한국의 봄, 벚꽃, 수채화 스타일

/model a gpt-4o
/model b claude-sonnet-4-6
```

---

## Plugins

amp는 외부 플러그인으로 기능을 확장할 수 있습니다. 플러그인은 `~/.amp/plugins/`에 설치됩니다.

### 플러그인 관리

```bash
# 설치
amp plugin install https://github.com/user/my-plugin   # GitHub 리포
amp plugin install /path/to/my-plugin/                 # 로컬 디렉토리
amp plugin install /path/to/single_plugin.py           # 단일 .py 파일

# 목록
amp plugin list

# 제거
amp plugin remove my-plugin

# 새 플러그인 만들기
amp plugin new my-plugin   # ~/.amp/plugins/my-plugin/ 스캐폴딩 생성
```

### REPL에서 플러그인 토글

```
\plugin list              # 등록된 플러그인 목록
\plugin on image_vision   # 플러그인 활성화
\plugin off image_gen     # 플러그인 비활성화
```

자세한 플러그인 개발 가이드: [`docs/plugin-guide.md`](docs/plugin-guide.md)

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
