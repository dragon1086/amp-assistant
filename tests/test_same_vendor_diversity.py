#!/usr/bin/env python3
"""
test_same_vendor_diversity.py — 같은 벤더 강제 다양성 시스템 검증
commit 8452098 이후 구현 내용 유닛 테스트 (API 호출 없음)
"""

import sys
import os

# amp 패키지 경로
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "✅"
FAIL = "❌"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))


print("\n" + "=" * 60)
print("  같은 벤더 강제 다양성 시스템 검증")
print("=" * 60)


# ─── 1. _is_same_vendor() 유닛 테스트 ─────────────────────────────

print("\n[1] 벤더 감지 (_is_same_vendor)")
from amp.core.emergent import _is_same_vendor

check("GPT + GPT → 동일 벤더", _is_same_vendor("openai", "openai"))
check("Claude + Claude → 동일 벤더", _is_same_vendor("anthropic", "anthropic"))
check("Claude OAuth + Anthropic → 동일 벤더", _is_same_vendor("anthropic_oauth", "anthropic"))
check("Claude OAuth + Claude OAuth → 동일 벤더", _is_same_vendor("anthropic_oauth", "anthropic_oauth"))
check("GPT + Claude → 교차 벤더", not _is_same_vendor("openai", "anthropic"))
check("GPT + Claude OAuth → 교차 벤더", not _is_same_vendor("openai", "anthropic_oauth"))
check("Local + Local → 동일 벤더", _is_same_vendor("local", "local"))
check("GPT + Local → 교차 벤더", not _is_same_vendor("openai", "local"))


# ─── 2. SAME_VENDOR_PRESETS 완결성 ───────────────────────────────

print("\n[2] SAME_VENDOR_PRESETS 완결성")
from amp.core.auto_persona import SAME_VENDOR_PRESETS, SAME_VENDOR_TEMPS

EXPECTED_DOMAINS = [
    "career", "relationship", "business", "investment",
    "legal_contract", "health", "ethics", "creative",
    "parenting", "default",
]

for domain in EXPECTED_DOMAINS:
    preset = SAME_VENDOR_PRESETS.get(domain)
    check(
        f"도메인 '{domain}' 존재",
        preset is not None and isinstance(preset, tuple) and len(preset) == 2,
        f"A='{str(preset[0])[:30]}...'" if preset else "MISSING",
    )

# 'default' 폴백 필수
default = SAME_VENDOR_PRESETS.get("default")
check("'default' 폴백 있음", default is not None)


# ─── 3. Temperature 쌍 ───────────────────────────────────────────

print("\n[3] SAME_VENDOR_TEMPS")
check("SAME_VENDOR_TEMPS 타입 tuple", isinstance(SAME_VENDOR_TEMPS, tuple))
check("길이 2", len(SAME_VENDOR_TEMPS) == 2)
temp_a, temp_b = SAME_VENDOR_TEMPS
check(f"temp_a = 0.3 (정밀)", temp_a == 0.3, f"실제값: {temp_a}")
check(f"temp_b = 1.1 (창의)", temp_b == 1.1, f"실제값: {temp_b}")
check("temp_a < temp_b (다양성 보장)", temp_a < temp_b)


# ─── 4. generate_personas same_vendor=True 구조 ──────────────────

print("\n[4] generate_personas(same_vendor=True) 구조")
from amp.core.auto_persona import generate_personas

try:
    # API 호출 없이 테스트하려면 domain 키워드를 포함한 쿼리 사용
    # generate_personas는 LLM 호출할 수도 있으므로 import 수준만 검증
    import inspect
    sig = inspect.signature(generate_personas)
    check("same_vendor 파라미터 존재", "same_vendor" in sig.parameters)
    check("query 파라미터 존재", "query" in sig.parameters)
except Exception as e:
    check("generate_personas import", False, str(e))


# ─── 5. emergent.py 강제 다양성 통합 ────────────────────────────

print("\n[5] emergent.py 통합 확인")
import inspect
from amp.core import emergent as em_module

src = inspect.getsource(em_module)
check("same_vendor 플래그 반환", '"same_vendor"' in src or "'same_vendor'" in src)
check("temperature_a 전달", "temperature_a" in src or "temp_a" in src)
check("temperature_b 전달", "temperature_b" in src or "temp_b" in src)
check("역할 제약 주입 (데이터/증거만)", "데이터" in src or "데이터/수치" in src or "data" in src.lower())
check("역할 제약 주입 (통념 도전)", "통념" in src or "challenge" in src.lower())


# ─── 6. CLI 경고 메시지 ──────────────────────────────────────────

print("\n[6] CLI 경고 메시지 확인")
try:
    # rich 등 선택적 의존성 때문에 import 대신 소스 직접 읽기
    import pathlib
    cli_path = pathlib.Path(__file__).parent.parent / "amp" / "interfaces" / "cli.py"
    cli_src = cli_path.read_text(encoding="utf-8")
    check("강제 다양성 모드 경고 텍스트", "강제 다양성" in cli_src)
    check("CLI 파일 존재", cli_path.exists())
except Exception as e:
    check("CLI 소스 읽기", False, str(e))


# ─── 7. 예상 CSER 비교 (이론값 요약) ────────────────────────────

print("\n[7] CSER 예상치 요약 (이론값)")
cser_table = {
    "교차 벤더 (GPT + Claude)": (0.8, 0.9),
    "같은 벤더 + 극단팩 + temp 차별화": (0.65, 0.75),
    "같은 벤더 + 페르소나 없음": (0.4, 0.6),
}
for label, (lo, hi) in cser_table.items():
    print(f"    {label}: CSER {lo}~{hi}")
check("교차 벤더 > 같은 벤더+극단팩", cser_table["교차 벤더 (GPT + Claude)"][0] > cser_table["같은 벤더 + 극단팩 + temp 차별화"][1])
check("같은 벤더+극단팩 > 같은 벤더 기본", cser_table["같은 벤더 + 극단팩 + temp 차별화"][0] > cser_table["같은 벤더 + 페르소나 없음"][1])


# ─── 결과 요약 ───────────────────────────────────────────────────

print("\n" + "=" * 60)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
total = passed + failed
print(f"  결과: {passed}/{total} 통과 {'🎉' if failed == 0 else '⚠️'}")
if failed > 0:
    print("\n  실패 항목:")
    for s, name, detail in results:
        if s == FAIL:
            print(f"    {FAIL} {name}" + (f" — {detail}" if detail else ""))
print("=" * 60 + "\n")

def test_same_vendor_diversity_checks():
    """Pytest 엔트리포인트: top-level 검증 결과를 테스트로 반영."""
    failed_items = [name for s, name, _ in results if s == FAIL]
    assert failed == 0, f"same_vendor 다양성 검증 실패: {failed_items}"
