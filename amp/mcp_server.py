"""
mcp_server.py — amp MCP Server
Multi-Agent Capability Registry System (MACRS)

amp의 능력을 외부 AI(록이/OpenClaw)가 MCP 프로토콜로 호출할 수 있게 노출.
JSON-RPC 2.0 over HTTP (FastAPI, port 3010)

지원 메서드:
  tools/list  — 사용 가능한 도구 목록
  tools/call  — 도구 실행

노출 도구:
  analyze      — 2-agent 독립 분석 (emergent 2-round)
  debate       — 4-round 심층 토론 (emergent 4-round)
  quick_answer — 단일 LLM 빠른 응답 (solo)

실행:
  uvicorn amp.mcp_server:app --port 3010 --host 127.0.0.1
  또는
  python -m amp.mcp_server
"""

import json
import logging
import os
import sys
from typing import Any

# amp 패키지 경로 등록
_AMP_ROOT = os.path.expanduser("~/amp")
if _AMP_ROOT not in sys.path:
    sys.path.insert(0, _AMP_ROOT)

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("[mcp_server] FastAPI/uvicorn 미설치. 설치: pip install fastapi uvicorn")
    sys.exit(1)

from amp.core import emergent, solo
from amp.config import load_config

logger = logging.getLogger(__name__)
app = FastAPI(title="amp MCP Server", version="1.0.0")

# ── 도구 정의 ────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "analyze",
        "description": (
            "2-agent 독립 분석 (emergent 2-round). "
            "두 AI가 독립적으로 분석 후 합성. CSER로 독창성 측정. "
            "전략 검토, 장단점 분석, 의사결정 지원에 최적."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "분석할 질문 또는 주제"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "debate",
        "description": (
            "4-round 심층 토론 (A제시→B반박→A재반박→B재반박→합성). "
            "비교 분석, 찬반 검토, 복잡한 결정에 최적. "
            "analyze보다 느리지만 더 깊은 분석."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "토론할 주제 또는 비교 대상"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "quick_answer",
        "description": (
            "단일 LLM 빠른 응답 (solo). "
            "간단한 사실 확인, 요약, 번역에 최적. "
            "가장 빠르고 저렴."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "질문 또는 요청"
                }
            },
            "required": ["query"]
        }
    },
]


# ── config 로드 ───────────────────────────────────────────────────

def _get_config() -> dict:
    """amp config 로드. 실패 시 기본값 반환."""
    try:
        return load_config()
    except Exception:
        return {
            "llm": {"provider": "anthropic_oauth", "model": "gpt-4o-mini"},
            "agents": {
                "agent_a": {"provider": "openai", "model": "gpt-4o-mini"},
                "agent_b": {"provider": "anthropic_oauth", "model": "claude-sonnet-4-6"},
            },
            "amp": {"default_mode": "auto", "kg_path": "~/.amp/kg.db"},
        }


# ── JSON-RPC 2.0 핸들러 ───────────────────────────────────────────

def _rpc_error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _rpc_result(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


async def _handle_tools_list(id_: Any, _params: dict) -> dict:
    """tools/list → 사용 가능한 도구 목록"""
    return _rpc_result(id_, {"tools": TOOLS})


async def _handle_tools_call(id_: Any, params: dict) -> dict:
    """tools/call → 도구 실행"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        return _rpc_error(id_, -32602, "name 파라미터 필수")

    query = arguments.get("query", "")
    if not query:
        return _rpc_error(id_, -32602, "query 파라미터 필수")

    config = _get_config()

    try:
        if tool_name == "analyze":
            result = emergent.run(query=query, context=[], config=config, rounds=2)
            content = _format_emergent_result(result)

        elif tool_name == "debate":
            result = emergent.run(query=query, context=[], config=config, rounds=4)
            content = _format_emergent_result(result)

        elif tool_name == "quick_answer":
            result = solo.run(query=query, context=[], config=config)
            content = result.get("answer", "")

        else:
            return _rpc_error(id_, -32601, f"알 수 없는 도구: {tool_name}")

        return _rpc_result(id_, {
            "content": [{"type": "text", "text": content}]
        })

    except Exception as e:
        logger.exception(f"도구 실행 오류: {tool_name}")
        return _rpc_error(id_, -32000, f"실행 오류: {str(e)[:200]}")


def _format_emergent_result(result: dict) -> str:
    """emergent 결과를 사람/AI가 읽기 좋은 형식으로 변환"""
    answer = result.get("answer", "")
    cser = result.get("cser")
    mode = result.get("mode", "emergent")
    rounds = result.get("rounds", 2)
    agent_a_label = result.get("agent_a_label", "Agent A")
    agent_b_label = result.get("agent_b_label", "Agent B")

    lines = [answer]

    if cser is not None:
        cser_emoji = "✅" if cser >= 0.30 else "⚠️"
        lines.append(f"\n📊 CSER: {cser:.3f} {cser_emoji} | 모드: {mode} ({rounds}-round)")
        lines.append(f"🤖 {agent_a_label} × {agent_b_label}")

    agreements = result.get("agreements", [])
    if agreements:
        lines.append(f"\n✅ 합의: {', '.join(agreements[:2])}")

    return "\n".join(lines)


# ── FastAPI 라우트 ────────────────────────────────────────────────

@app.post("/")
async def handle_rpc(request: Request) -> JSONResponse:
    """JSON-RPC 2.0 엔드포인트"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "JSON 파싱 오류"))

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "ping":
        return JSONResponse(_rpc_result(rpc_id, {"status": "ok", "service": "amp-mcp"}))
    elif method == "tools/list":
        return JSONResponse(await _handle_tools_list(rpc_id, params))
    elif method == "tools/call":
        return JSONResponse(await _handle_tools_call(rpc_id, params))
    else:
        return JSONResponse(_rpc_error(rpc_id, -32601, f"지원하지 않는 메서드: {method}"))


@app.get("/health")
async def health():
    """헬스체크 엔드포인트"""
    return {"status": "ok", "service": "amp-mcp-server", "version": "1.0.0"}


# ── 단독 실행 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[amp-mcp] 서버 시작: http://127.0.0.1:3010")
    uvicorn.run(app, host="127.0.0.1", port=3010, log_level="info")
