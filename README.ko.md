# amp — AI 토론 엔진

> **두 AI가 싸운다. 당신은 더 나은 답을 얻는다.**

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**다른 언어로 읽기:** [English](README.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [Español](README.es.md)

---

## 왜 amp인가?

AI 하나는 한계가 있습니다 — 같은 데이터로 훈련됐고, 같은 편향을 갖고 있으며, 언제나 "안전한" 답을 줍니다. **amp는 두 개의 독립적인 AI를 병렬로 실행하고, 서로 논쟁하게 한 뒤, 두 관점을 합성해 더 나은 답을 만듭니다.**

```
당신의 질문
       │
       ├─────────────────────────────────────┐
       ▼                                     ▼
  Agent A (GPT-5)                     Agent B (Claude)
  [독립 분석]                           [독립 분석]
       │                                     │
       └─────────────┬───────────────────────┘
                     ▼
               Reconciler (합성기)
                     │
                     ▼
         최종 답변  +  CSER 점수
```

**CSER** (Cross-agent Semantic Entropy Ratio): 두 AI가 얼마나 다르게 생각했는지 측정하는 지표. 높을수록 → 더 독립적인 사고 → 더 좋은 합성 결과.

---

## 설치

```bash
pip install amp-reasoning
amp init        # 대화형 설정 (~1분)
```

**OAuth 무료 사용** (API 키 불필요 — ChatGPT Plus + Claude Max 구독 필요):
```bash
amp login       # 브라우저로 두 제공사 OAuth 인증
```

**원클릭 설치:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## 빠른 시작

```bash
# 바로 물어보기
amp "비트코인 지금 사야 할까?"
amp "2026년에 새 프로젝트 시작한다면 React vs Vue 뭐가 나아?"
amp "Rust vs Go, 진짜 차이점이 뭐야?"

# 4라운드 심층 토론 (더 오래 걸리지만 훨씬 깊음)
amp --mode emergent "AGI가 2028년 전에 올 수 있을까?"

# MCP 서버 시작 (Claude Desktop, Cursor, OpenClaw 등)
amp serve
```

---

## 동작 원리

### 기본 모드 — 2라운드 독립 분석
Agent A와 B가 **서로의 답변을 모른 채** 독립적으로 분석합니다.
진짜 독립성 보장 → 높은 CSER → 더 나은 합성.

### Emergent 모드 — 4라운드 구조화된 토론
```
Round 1:  Agent A 분석
Round 2:  Agent B가 A의 논리 반박
Round 3:  Agent A가 B의 반박에 재반론
Round 4:  Agent B 최종 반박
              └──► Reconciler가 합성
```

### CSER Gate
두 AI가 너무 비슷하게 동의하면 (CSER < 0.30), amp가 자동으로 4라운드 토론으로 
업그레이드해 더 다양한 관점을 강제로 이끌어냅니다.

### 지식 그래프 (Knowledge Graph)
amp는 로컬 지식 그래프 (`~/.amp/kg.db`)를 유지합니다. 세션이 쌓일수록 당신의 특정 도메인에 더 정확해집니다.

---

## 설정

```bash
amp init   # 대화형 마법사
amp setup  # 전체 설정 (모델, 텔레그램 봇, 플러그인)
```

또는 `~/.amp/config.yaml` 직접 편집:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2             # gpt-5.2 | gpt-5.4 | gpt-5.4-mini
    reasoning_effort: high     # none | low | medium | high | xhigh

  agent_b:
    provider: anthropic        # ANTHROPIC_API_KEY 있으면 가장 빠름
    # provider: anthropic_oauth  # Claude OAuth 무료 사용 (조금 느림)
    model: claude-sonnet-4-6

amp:
  parallel: true      # Agent A+B 병렬 실행 (기본: true, ~50% 빠름)
  timeout: 90         # 에이전트당 타임아웃 (초)
  kg_path: ~/.amp/kg.db
```

### 제공사 옵션

| 제공사 | 속도 | 비용 | 조건 |
|--------|------|------|------|
| `openai` | ⚡⚡⚡ | 유료 | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **무료** | ChatGPT Plus/Pro + `amp login` |
| `anthropic` | ⚡⚡⚡ | 유료 | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **무료** | Claude Max/Pro + `amp login` |
| `gemini` | ⚡⚡⚡ | 유료 | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | 저렴 | `DEEPSEEK_API_KEY` |
| `mistral` | ⚡⚡⚡ | 저렴 | `MISTRAL_API_KEY` |
| `xai` | ⚡⚡⚡ | 유료 | `XAI_API_KEY` |
| `local` | ⚡⚡ | 무료 | Ollama 실행 중 |

**완전 무료 조합 (ChatGPT Plus + Claude Max 구독자):**
```bash
amp login
# → openai_oauth × anthropic_oauth 자동 설정
# → API 비용 $0
```

---

## MCP 서버

Claude Desktop, Cursor, OpenClaw 등 MCP 호환 클라이언트와 연동:

```bash
amp serve   # http://127.0.0.1:3010 에서 시작
```

MCP 설정에 추가:
```json
{
  "amp": {
    "url": "http://127.0.0.1:3010"
  }
}
```

| 도구 | 설명 | 예상 시간 |
|------|------|----------|
| `analyze` | 2라운드 독립 분석 | 15–30초 |
| `debate` | 4라운드 구조화된 토론 | 30–60초 |
| `quick_answer` | 단일 LLM 빠른 답변 | ~3초 |

---

## Docker

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

# docker-compose 사용
OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## Python API

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(
    query="백엔드에 Rust와 Go 중 뭘 써야 할까?",
    context=[],
    config=config,
)

print(result["answer"])
print(f"CSER:     {result['cser']:.2f}")        # 두 AI가 얼마나 다르게 생각했는지
print(f"합의점:   {result['agreements']}")
print(f"의견 차이: {result['conflicts']}")
```

---

## 성능 (2026-03 기준, Apple M 시리즈, 병렬 모드)

| 구성 | 평균 응답시간 | 쿼리당 비용 |
|------|-------------|------------|
| GPT-5.2 + Claude Sonnet (API, 병렬) | ~18초 | $0.03–0.08 |
| GPT-5.2 + Claude OAuth (병렬) | ~35초 | ~$0.01 |
| GPT-5.2 + GPT-5.2 (동일 벤더) | ~15초 | $0.02–0.05 |

병렬 A+B 실행으로 순차 대비 **~50% 빠름** (v0.1.0+).

---

## 왜 교차 벤더인가?

GPT와 Claude는 서로 다른 회사가, 서로 다른 데이터로, 서로 다른 정렬 방법으로 훈련했습니다. 같은 질문에 진짜로 다른 의견을 가질 가능성이 높습니다. 이것이 amp의 핵심 통찰 — **교차 벤더 합성은 단일 벤더 셀프 토론보다 더 나은 답을 만든다.**

동일 벤더 (GPT+GPT)도 동작합니다 — amp가 자동으로 페르소나를 극단적으로 다르게 설정해 다양성을 확보합니다.

---

## 기여하기

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

큰 변경사항은 먼저 이슈를 열어주세요. PR 환영합니다.

---

## 라이선스

MIT © 2026 amp contributors
