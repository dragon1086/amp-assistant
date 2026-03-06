# amp — AI Debate Engine

> **Two AIs argue. You get a better answer.**

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Why amp?

A single AI has blind spots — it trained on the same data, has the same biases, and often gives the "safe" answer. **amp makes two independent AIs argue about your question, then synthesizes the best answer from both.**

```
Your question
     ↓
Agent A (GPT-5.2) ──────────────── Agent B (Claude Sonnet)
    [독립 분석, 병렬]                    [독립 분석, 병렬]
         ↓                                    ↓
         └─────────── Reconciler ─────────────┘
                           ↓
              Better Answer + CSER score
              (두 AI가 얼마나 다른 시각을 가졌는지)
```

**CSER** (Cross-agent Semantic Entropy Ratio): 두 AI의 의견 다양성 측정 지표. 높을수록 더 독립적인 사고.

---

## Install

```bash
pip install amp-reasoning
amp init   # API 키 설정 (1분)
```

**원클릭 설치:**
```bash
curl -fsSL https://raw.githubusercontent.com/amp-reasoning/amp/main/install.sh | bash
```

---

## Quick Start

```bash
# 바로 사용
amp "비트코인 지금 사야 할까?"
amp "React vs Vue in 2026 — which should I pick?"
amp "스타트업에서 CTO 역할을 맡아야 할까?"

# 4라운드 심층 토론 (더 오래 걸리지만 더 깊음)
amp --mode emergent "AGI가 2027년 전에 가능할까?"

# MCP 서버 (Claude Desktop, Cursor, OpenClaw 연동)
amp serve
```

---

## How It Works

### 2-Round (기본): 독립 분석
Agent A와 B가 **서로의 답을 모른 채** 독립적으로 분석.
→ 진짜 독립적 사고 → 높은 CSER → 더 좋은 합성

### 4-Round (심층): 순차 토론
```
Round 1: A 분석
Round 2: B가 A를 반박
Round 3: A가 B의 반박에 재반론
Round 4: B 최종 반박
        → Reconciler 합성
```

### CSER Gate
두 AI 답변이 너무 비슷하면 (CSER < 0.30) → 자동으로 4-round로 업그레이드.
더 다양한 시각을 강제로 끌어냄.

---

## Configuration

```bash
amp init  # 대화형 설정
```

또는 `~/.amp/config.yaml` 직접 편집:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2          # 최신 GPT-5 계열
    reasoning_effort: medium # none | low | medium | high | xhigh

  agent_b:
    provider: anthropic     # ANTHROPIC_API_KEY 있으면 (빠름)
    # provider: anthropic_oauth  # Claude OAuth 무료 (느림, subprocess)
    model: claude-sonnet-4-6

amp:
  parallel: true   # Agent A+B 병렬 실행 (기본: true, ~50% 속도 향상)
  timeout: 90      # 에이전트당 타임아웃 (초)
  kg_path: ~/.amp/kg.db  # 지식 그래프 저장 경로
```

### Provider 옵션

| provider | 속도 | 비용 | 조건 |
|----------|------|------|------|
| `openai` | ⚡⚡⚡ | 유료 | OPENAI_API_KEY |
| `anthropic` | ⚡⚡⚡ | 유료 | ANTHROPIC_API_KEY |
| `anthropic_oauth` | ⚡ | 무료 | Claude CLI 설치 |
| `local` | ⚡⚡ | 무료 | Ollama 실행 중 |

---

## MCP Server

Claude Desktop, Cursor, OpenClaw 등 MCP 호환 클라이언트에서 사용:

```bash
amp serve  # http://127.0.0.1:3010
```

MCP 설정에 추가:
```json
{
  "amp": {
    "url": "http://127.0.0.1:3010"
  }
}
```

사용 가능한 도구:
- `analyze` — 2-round 독립 분석 (15~30초)
- `debate` — 4-round 심층 토론 (30~60초)
- `quick_answer` — 단일 LLM 빠른 답변 (3초)

---

## Docker

```bash
# 서버만
docker run -e OPENAI_API_KEY=... -e ANTHROPIC_API_KEY=... -p 3010:3010 ghcr.io/amp-reasoning/amp

# docker-compose
OPENAI_API_KEY=... ANTHROPIC_API_KEY=... docker-compose up
```

---

## Python API

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(query="Should I use Rust or Go?", context=[], config=config)

print(result["answer"])
print(f"CSER: {result['cser']:.2f}")  # 두 AI 시각 다양성
print(f"Agreements: {result['agreements']}")
```

---

## Performance (2026-03 기준)

| 구성 | 평균 응답시간 | 비용 |
|------|-------------|------|
| GPT-5.2 + Claude Sonnet (API, 병렬) | ~18초 | $0.03~0.08 |
| GPT-5.2 + Claude OAuth (병렬) | ~35초 | $0.01~0.03 |
| GPT-5.2 + GPT-5.2 (같은 벤더) | ~15초 | $0.02~0.05 |

병렬화로 기존 대비 **~50% 속도 향상** (v0.1.0+)

---

## Why Cross-Vendor?

GPT와 Claude는 다른 회사가, 다른 데이터로, 다른 방법으로 훈련했습니다. 같은 질문에 다른 관점을 가질 가능성이 높습니다. 이것이 amp의 핵심 — 교차 벤더 합성.

같은 벤더 (GPT+GPT)도 동작하지만, amp는 자동으로 페르소나를 극단적으로 다르게 설정해 다양성을 확보합니다.

---

## Contributing

```bash
git clone https://github.com/amp-reasoning/amp
cd amp
pip install -e ".[dev]"
pytest
```

---

## License

MIT © 2026 amp contributors
