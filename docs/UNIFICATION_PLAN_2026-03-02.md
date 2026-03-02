# amp 통합 방향 (2026-03-02)

## 결론
- **프로덕션 단일 소스: `~/amp`**
- `~/emergent`는 **연구/실험 전용** (KG 이론, 메트릭, 논문)
- `~/emergent/amp.py`, `~/emergent/telegram_bot.py`는 기능 참고용으로만 유지하고, 제품 기능은 `~/amp`에 통합

## 왜 이 방향인가
`~/amp`는 이미 다음을 갖춤:
- 이미지 생성/비전 플러그인
- 플러그인 레지스트리/로더
- SQLite KG 연동
- 사용자 설정 저장
- Telegram 인터페이스 + CLI 인터페이스

`~/emergent`는 실험 코드 중심:
- 빠른 프로토타이핑 유리
- 그러나 제품 안정성/확장성 측면에서 분기 유지 비용 큼

## 실행 원칙
1. 중복 구현 금지: 새 기능은 `~/amp`에만 추가
2. `~/emergent`의 유용한 아이디어만 선택적 이식
3. 이식 시 회귀 테스트 + Telegram 실사용 검증 필수

## 기능별 통합 계획

### 1) 이미지 생성
- 유지: `~/amp/amp/plugins/image_gen.py`
- 작업: 백엔드별 에러 메시지 통일 + timeout/retry 공통화

### 2) 플러그인 시스템
- 유지: `BasePlugin`, `PluginRegistry`, `skill_loader`
- 작업: plugin capability metadata(권한 스코프) 추가

### 3) KG 연동
- 유지: `amp/core/kg.py` + ontological tags
- 작업: 저장 정책 통일 (Episodic/Semantic/Procedural)

### 4) 설정 시스템
- 유지: `~/.amp/config.yaml` + user_config.db
- 작업: 모델/라우팅/플러그인 설정 schema 명시 + 검증기 추가

### 5) 토론 라운드
- 현재: 2-agent + reconciler
- 목표: **적응형 라운드(2/4)**
  - low complexity: 2라운드
  - high complexity: 4라운드(A→B→A→B→합성)
- 출처: `~/emergent/amp.py` 아이디어를 `~/amp/core/emergent.py`에 이식

## 자연어 실행(Claude Code) 방향
- 패턴 매칭 플러그인이 아니라, **LLM tool-calling**로 구현
- `llm_factory.py`에 tool schema 등록:
  - `execute_task(tool="claude_code", task, cwd, timeout)`
- emergent/solo/pipeline 공통으로 tool-call 처리 루프 추가
- 안전 정책:
  - 허용된 workdir만 실행
  - destructive 명령 차단
  - 결과/에러를 대화로 반환

## 즉시 적용 상태
- `claude_executor`는 기본 비활성화 (`enabled_by_default=False`)
- 자연어 자동 인터셉트 비활성화 (명시적 `/claude`만)

## 다음 구현 순서
1. GPT-5.x `reasoning_effort` 지원 (`llm_factory.py`)
2. 적응형 4라운드 토론 이식 (`emergent.py`)
3. tool-calling 실행 루프 추가 (`llm_factory.py` + runtime)
4. Telegram E2E 테스트 (실사용 질문 20개)
5. 문서/마이그레이션 가이드
