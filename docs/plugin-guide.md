# amp 플러그인 개발자 가이드

amp 플러그인은 `~/.amp/plugins/`에 설치되며, 텔레그램 봇과 CLI REPL 모두에서 동작합니다.

---

## 플러그인 종류

| 종류 | 파일 구성 | 언제 사용 |
|------|-----------|-----------|
| **Markdown-only** | `SKILL.md`만 있음 | LLM 시스템 프롬프트 주입만 필요할 때 |
| **Python 플러그인** | `SKILL.md` + `scripts/main.py` | 메시지 가로채기, 외부 API 호출, 커스텀 로직 |

**Markdown-only** 플러그인은 Python 없이도 LLM의 성격이나 지식을 확장할 수 있습니다.
**Python 플러그인**은 특정 메시지 패턴을 가로채 완전히 커스텀 응답을 반환합니다.

---

## 플러그인 디렉토리 구조

```
~/.amp/plugins/
  my-plugin/
    SKILL.md          # 메타데이터 + Markdown-only 시스템 프롬프트
    scripts/
      main.py         # Python 플러그인 구현 (선택사항)
```

단일 `.py` 파일도 플러그인으로 사용할 수 있습니다:
```
~/.amp/plugins/
  quick_plugin.py     # 단일 파일 플러그인
```

---

## SKILL.md 포맷

```markdown
---
name: my-plugin
description: 플러그인 한 줄 설명
enabled_by_default: true
---

# My Plugin

## 역할

당신은 ... 전문가입니다. 사용자가 ... 을 물어보면 ...

## 지식

- 항목 1
- 항목 2
```

### SKILL.md 필드

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `name` | string | 디렉토리명 | 플러그인 식별자 (`amp plugin list`에 표시) |
| `description` | string | `""` | 한 줄 설명 |
| `enabled_by_default` | bool | `true` | `false`면 `/plugin on <name>` 으로 수동 활성화 필요 |

---

## BasePlugin 메서드

`scripts/main.py`에서 `BasePlugin`을 상속하여 구현합니다.

```python
from amp.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    name = "my-plugin"
    description = "플러그인 설명"
    enabled_by_default = True
```

### 필수 구현 메서드

#### `can_handle(update) -> bool`

이 플러그인이 메시지를 처리할지 여부를 반환합니다.
`True`를 반환하면 `handle()`이 호출되고, amp 기본 라우팅은 건너뜁니다.

```python
def can_handle(self, update) -> bool:
    text = getattr(getattr(update, "message", None), "text", None) or ""
    return text.lower().startswith("!weather")
```

#### `handle(update, context, config, user_config) -> str | None`

실제 처리 로직입니다. 응답 문자열을 반환하거나, `None`을 반환합니다.

- **문자열 반환**: amp가 자동으로 텔레그램/REPL에 전송
- **`None` 반환**: 플러그인이 직접 `update.message.reply_text()`를 호출한 경우

```python
async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
    text = update.message.text or ""
    city = text.removeprefix("!weather").strip() or "서울"
    # ... API 호출 등
    return f"🌤️ {city} 날씨: 맑음, 15°C"
```

### 선택 구현 메서드

#### `get_system_prompt() -> str | None`

LLM 시스템 프롬프트에 추가로 주입할 텍스트를 반환합니다.
주로 Markdown-only 플러그인에서 사용하지만, Python 플러그인도 구현할 수 있습니다.

```python
def get_system_prompt(self) -> str | None:
    return "당신은 주식 투자 전문가입니다. 항상 리스크를 함께 언급하세요."
```

#### `get_commands() -> list[tuple[str, str]]`

봇에 등록할 커맨드 목록입니다. `(command, description)` 튜플 리스트.

```python
def get_commands(self) -> list[tuple[str, str]]:
    return [("weather", "날씨 조회: /weather 서울")]
```

#### `setup(app, config) -> None`

봇 시작 시 한 번 호출됩니다. 추가 핸들러 등록 등에 사용합니다.

```python
def setup(self, app, config: dict | None = None) -> None:
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("weather", self._cmd_weather))
```

---

## 예시 1: Markdown-only 플러그인 (투자 조언가)

Python 없이 LLM 페르소나만 바꾸는 가장 간단한 형태입니다.

**파일**: `~/.amp/plugins/stock-advisor/SKILL.md`

```markdown
---
name: stock-advisor
description: 주식 투자 조언 전문가 페르소나 주입
enabled_by_default: false
---

# 주식 투자 조언가

당신은 10년 경력의 퀀트 투자 전문가입니다.

## 행동 지침

- 모든 투자 조언에는 반드시 리스크와 면책 조항을 포함합니다
- 수익률보다 리스크 관리를 먼저 언급합니다
- PER, PBR 등 수치는 최신 데이터를 기준으로 설명하고, 모를 경우 솔직히 인정합니다
- "확실하다"거나 "무조건"이라는 표현은 사용하지 않습니다
```

**설치 및 사용**:
```bash
amp plugin install ~/.amp/plugins/stock-advisor
# 텔레그램에서
/plugin on stock-advisor
삼성전자 지금 사도 될까?
```

---

## 예시 2: Python 플러그인 (날씨 조회)

특정 키워드로 시작하는 메시지를 가로채 외부 API를 호출합니다.

**파일**: `~/.amp/plugins/weather/SKILL.md`

```markdown
---
name: weather
description: !weather <도시> 로 날씨 조회
enabled_by_default: true
---
```

**파일**: `~/.amp/plugins/weather/scripts/main.py`

```python
"""날씨 플러그인 — !weather <도시> 로 날씨 조회."""

import httpx
from amp.plugins.base import BasePlugin


class WeatherPlugin(BasePlugin):
    name = "weather"
    description = "!weather <도시> 로 날씨 조회"
    enabled_by_default = True

    def can_handle(self, update) -> bool:
        text = getattr(getattr(update, "message", None), "text", None) or ""
        return text.lower().startswith("!weather")

    async def handle(self, update, context, config: dict, user_config: dict) -> str | None:
        text = update.message.text or ""
        city = text.removeprefix("!weather").strip() or "Seoul"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://wttr.in",
                    params={"format": "3", "lang": "ko"},
                    headers={"User-Agent": "amp-weather-plugin/1.0"},
                )
                resp.raise_for_status()
                return f"🌤️ {resp.text.strip()}"
        except Exception as e:
            return f"❌ 날씨 조회 실패: {e}"

    def get_commands(self) -> list[tuple[str, str]]:
        return [("weather", "날씨 조회 (예: !weather 서울)")]
```

**설치**:
```bash
amp plugin install ~/.amp/plugins/weather
amp plugin list   # 확인
```

---

## 플러그인 스캐폴딩 자동 생성

```bash
amp plugin new my-plugin
```

`~/.amp/plugins/my-plugin/` 에 `SKILL.md`와 `scripts/main.py` 보일러플레이트를 자동 생성합니다.

---

## 주의사항

- `can_handle()`에서 `True`를 반환하면 amp 기본 라우팅(solo/pipeline/emergent)이 **건너뜁니다**
- 여러 플러그인이 `can_handle()` = `True`인 경우, 등록 순서 첫 번째 플러그인만 실행됩니다
- `handle()`에서 예외가 발생하면 에러 메시지가 사용자에게 전송되고 다른 플러그인은 실행되지 않습니다
- Markdown-only 플러그인(`get_system_prompt()` 구현)은 amp 라우팅을 막지 않고, LLM 프롬프트에만 영향을 줍니다
