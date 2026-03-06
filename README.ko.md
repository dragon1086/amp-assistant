<div align="center">

![amp 배너](docs/assets/banner.png)

<h3>두 AI가 싸운다. 당신은 더 나은 답을 얻는다.</h3>

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning?color=7c3aed&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Downloads](https://img.shields.io/pypi/dm/amp-reasoning?color=0891b2&style=flat-square)](https://pypi.org/project/amp-reasoning/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

**[빠른 시작](#설치)** · **[작동 원리](#작동-원리)** · **[설정](#설정)** · **[MCP 서버](#mcp-서버)**

<br/>

**다른 언어:** [English](README.md) · [日本語](README.ja.md) · [中文](README.zh.md) · [Español](README.es.md)

</div>

---

## AI 하나에게만 물어보는 문제

AI 하나는 한계가 있습니다. 같은 데이터로 학습했고, 같은 편향을 갖고 있으며, 가장 "정확한" 답이 아니라 당신을 만족시킬 것 같은 답을 최적화합니다.

**amp는 두 개의 독립적인 AI 에이전트를 병렬로 실행하고, 토론하게 한 뒤, 두 관점을 합성해 더 나은 답을 만듭니다.**

<div align="center">

![아키텍처 다이어그램](docs/assets/architecture.png)

</div>

---

## 설치

```bash
pip install amp-reasoning
```

**방법 1 — API 키** (가장 빠름, 20초 이내):
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
amp init
```

**방법 2 — OAuth 무료** (ChatGPT Plus + Claude Max 구독 필요):
```bash
amp login    # 브라우저 OAuth, API 키 불필요, 비용 = $0
```

**방법 3 — 원클릭 설치:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## 데모

<div align="center">

![amp 터미널 데모](docs/assets/demo.svg)

</div>

---

## 작동 원리

amp는 **CSER(Cross-agent Semantic Entropy Ratio)**로 두 AI가 같은 질문에 얼마나 다르게 접근하는지 측정합니다. 사고가 독립적일수록 합성 품질이 높아집니다.

### 기본 모드 — 2라운드 병렬 분석

```
질문 ──┬──► Agent A (GPT-5)    ──► 독립 분석
       └──► Agent B (Claude)   ──► 독립 분석
                  │
                  ▼
           Reconciler 합성
                  │
                  ▼
  답변 + CSER 점수 + 합의점 + 의견 차이
```

Agent A와 B는 **병렬**로 실행되며 서로의 작업을 절대 볼 수 없습니다. 진짜 독립성을 보장하고 CSER을 최대화합니다.

### Emergent 모드 — 4라운드 구조적 토론

더 깊이 파고들어야 할 때 (또는 CSER < 0.30이어서 자동 업그레이드될 때):

```
Round 1 ── Agent A 분석
Round 2 ── Agent B가 A의 논리 반박
Round 3 ── Agent A가 B의 반박에 재반론
Round 4 ── Agent B 최종 반박
                │
                ▼
       Reconciler가 모든 라운드 합성
```

### 지식 그래프

amp는 모든 쿼리에서 로컬 지식 그래프(`~/.amp/kg.db`)를 구축합니다. 시간이 지날수록 도메인 컨텍스트가 쌓여 합성 품질이 개선됩니다.

---

## 설정

```bash
amp init    # 대화형 설정 마법사
```

`~/.amp/config.yaml`:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2              # gpt-5.2 · gpt-5.4 · gpt-5.4-mini
    reasoning_effort: high      # none · low · medium · high · xhigh

  agent_b:
    provider: anthropic         # 또는: anthropic_oauth (무료, 느림)
    model: claude-sonnet-4-6    # claude-opus-4-6 · claude-haiku-4-6

amp:
  parallel: true        # A+B 병렬 실행 (기본: true, ~50% 빠름)
  timeout: 90           # 에이전트당 타임아웃 (초)
  kg_path: ~/.amp/kg.db
```

### 지원 제공사

| 제공사 | 속도 | 비용 | 설정 |
|--------|:----:|------|------|
| `openai` | ⚡⚡⚡ | ~$0.03–0.08/q | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **무료** | ChatGPT Plus + `amp login` |
| `anthropic` | ⚡⚡⚡ | ~$0.03–0.08/q | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **무료** | Claude Max + `amp login` |
| `gemini` | ⚡⚡⚡ | ~$0.01–0.04/q | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | ~$0.001/q | `DEEPSEEK_API_KEY` |
| `mistral` | ⚡⚡⚡ | ~$0.002/q | `MISTRAL_API_KEY` |
| `xai` | ⚡⚡⚡ | ~$0.02/q | `XAI_API_KEY` |
| `local` | ⚡⚡ | 무료 | Ollama 실행 중 |

> **팁:** 다른 벤더의 제공사를 섞으면 다양성이 최대화됩니다.
> `openai` × `anthropic` 조합이 실제로 가장 높은 CSER을 보입니다.

---

## MCP 서버

**Claude Desktop**, **Cursor**, **Windsurf**, **OpenClaw** 등
[MCP 호환](https://modelcontextprotocol.io) 클라이언트와 연동됩니다.

```bash
amp serve   # http://127.0.0.1:3010 에서 시작
```

MCP 설정 파일에 추가:
```json
{
  "mcpServers": {
    "amp": {
      "url": "http://127.0.0.1:3010"
    }
  }
}
```

사용 가능한 도구:

| 도구 | 기능 | 예상 시간 |
|------|-----|:--------:|
| `analyze` | 2라운드 병렬 분석 | 15–30초 |
| `debate` | 4라운드 구조적 토론 | 30–60초 |
| `quick_answer` | 단일 모델 빠른 답변 | ~3초 |

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

print(result["answer"])                          # 합성된 최종 답변
print(f"CSER: {result['cser']:.2f}")             # 0–1, 두 AI의 의견 차이
print(f"합의점:   {result['agreements']}")
print(f"의견 차이: {result['conflicts']}")
```

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

## 성능

Apple M 시리즈, 2026-03, 병렬 모드 기준:

| 구성 | p50 지연 | p95 지연 | 쿼리당 비용 |
|------|:-------:|:-------:|:---------:|
| GPT-5.2 × Claude Sonnet (API) | 18초 | 28초 | $0.03–0.08 |
| GPT-5.2 × Claude OAuth | 32초 | 48초 | ~$0.01 |
| GPT-5.2 × DeepSeek V3 | 15초 | 22초 | ~$0.005 |
| GPT-5.2 × GPT-5.2 (동일 벤더) | 15초 | 20초 | $0.02–0.05 |

병렬 A+B 실행으로 순차 대비 **~50% 빠름** (v0.1.0+).

---

## 교차 벤더 합성이 효과적인 이유

GPT와 Claude는 서로 다른 회사가, 서로 다른 코퍼스로, 서로 다른 정렬 기법으로 학습했습니다. 같은 모델의 두 인스턴스보다 더 자주, 더 의미 있게 의견이 갈립니다.

동일 벤더 쌍(예: GPT+GPT)도 동작합니다. amp가 자동으로 각 에이전트에 극단적으로 반대되는 페르소나를 부여해 다양성을 최대화합니다. 하지만 교차 벤더가 자연스럽게 더 높은 CSER을 만들어냅니다.

---

## 기여하기

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

큰 PR 전에 이슈를 먼저 열어주세요. 모든 기여를 환영합니다.

---

## 라이선스

MIT © 2026 amp contributors
