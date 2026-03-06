#!/usr/bin/env bash
# amp-reasoning PyPI 릴리즈 스크립트
# 사용법: ./scripts/release.sh [버전] [--upload]
# 예시:   ./scripts/release.sh 0.1.2
#         ./scripts/release.sh 0.1.2 --upload  (직접 PyPI 업로드)

set -e
cd "$(dirname "$0")/.."

VERSION="${1:-}"
UPLOAD="${2:-}"

if [[ -z "$VERSION" ]]; then
    echo "사용법: $0 <버전> [--upload]"
    echo "예시:   $0 0.1.2"
    echo "       $0 0.1.2 --upload"
    exit 1
fi

echo "🔖 amp-reasoning v${VERSION} 릴리즈 준비"

# 1. 버전 업데이트
echo "→ pyproject.toml 버전 업데이트..."
sed -i '' "s/^version = .*/version = \"${VERSION}\"/" pyproject.toml

echo "→ amp/__init__.py 버전 업데이트..."
sed -i '' "s/__version__ = .*/__version__ = \"${VERSION}\"/" amp/__init__.py

# 2. 빌드
echo "→ 빌드 중..."
rm -rf dist/
python3 -m build

# 3. Twine 검증
echo "→ 패키지 검증..."
python3 -m twine check dist/*

# 4. 로컬 설치 테스트
echo "→ 로컬 설치 테스트..."
python3 -m venv /tmp/amp-release-test-venv --clear
/tmp/amp-release-test-venv/bin/pip install dist/amp_reasoning-${VERSION}-py3-none-any.whl -q
/tmp/amp-release-test-venv/bin/amp --help > /dev/null && echo "   ✅ amp --help OK"

# 5. Git 태그
echo "→ Git 커밋 & 태그..."
git add pyproject.toml amp/__init__.py
git commit -m "chore: bump version to ${VERSION}"
git tag "v${VERSION}"

if [[ "$UPLOAD" == "--upload" ]]; then
    # 직접 업로드 (PYPI_TOKEN 필요)
    if [[ -z "$PYPI_TOKEN" ]]; then
        echo "❌ PYPI_TOKEN 환경변수가 없어요!"
        echo "   export PYPI_TOKEN='pypi-xxxxx' 후 재시도"
        exit 1
    fi
    echo "→ PyPI 업로드..."
    TWINE_PASSWORD="$PYPI_TOKEN" TWINE_USERNAME="__token__" \
        python3 -m twine upload dist/*
    echo "✅ PyPI 업로드 완료!"
    echo "   pip install amp-reasoning==${VERSION}"
else
    echo ""
    echo "✅ 빌드 완료!"
    echo ""
    echo "📦 배포 방법 (택1):"
    echo ""
    echo "  A) GitHub Actions 자동 배포 (추천):"
    echo "     git push origin main --tags"
    echo "     → GitHub Actions가 자동으로 PyPI에 배포"
    echo ""
    echo "  B) 직접 업로드:"
    echo "     export PYPI_TOKEN='pypi-xxxxx'"
    echo "     ./scripts/release.sh ${VERSION} --upload"
fi
