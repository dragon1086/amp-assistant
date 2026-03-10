# Changelog

## [0.2.0] - 2026-03-10
### Changed
- `gpt-5-mini` hardcoding replaced with configurable `fast_model` (default: `gpt-5.4`)
- New `AMP_FAST_MODEL` env var and `llm.fast_model` config key
- `amp/config.py`: added `get_fast_model()` helper
### Added
- Tests for `get_fast_model()` and pipeline defaults (`tests/test_core.py`)
- `CHANGELOG.md` (this file)

## [0.1.1] - 2026-03-09
### Fixed
- CI: remove SystemExit from pytest collection in same_vendor test
- Reconciler: fix gpt-5-mini empty answer bug

## [0.1.0] - Initial release
- Two-agent emergent reasoning engine
- Auto-persona selection, CSER metric, KG memory
