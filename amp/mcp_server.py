"""
mcp_server.py — amp MCP Server (Streamable HTTP)
Multi-Agent Capability Registry System (MACRS)

MCP 2025-03-26 스펙: Streamable HTTP
- 단일 POST 엔드포인트
- Accept: application/json → 일반 JSON 응답 (빠른 툴)
- Accept: text/event-stream → SSE 스트리밍 응답 (긴 태스크)
- analyze/debate: SSE로 진행상황 실시간 전달 (15~30초)
- quick_answer: 일반 JSON (빠름)

실행: uvicorn amp.mcp_server:app --port 3010 --host 127.0.0.1
"""

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncGenerator
from typing import Any

_AMP_ROOT = os.path.expanduser("~/amp")
if _AMP_ROOT not in sys.path:
    sys.path.insert(0, _AMP_ROOT)

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
except ImportError:
    print("[mcp_server] FastAPI/uvicorn 미설치. 설치: pip install fastapi uvicorn")
    sys.exit(1)

from amp.core import emergent, solo
from amp.config import load_config

logger = logging.getLogger(__name__)
app = FastAPI(title="amp MCP Server (Streamable HTTP)", version="2.0.0")

# ── 도구 정의 ────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "analyze",
        "description": (
            "2-agent 독립 분석 (emergent 2-round). "
            "GPT × Claude가 독립 분석 후 합성. CSER로 독창성 측정. "
            "전략 검토·장단점·의사결정에 최적. 스트리밍 지원 (15~30초)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "분석할 질문"}},
            "required": ["query"],
        },
    },
    {
        "name": "debate",
        "description": (
            "4-round 심층 토론 (A제시→B반박→A재반박→B재반박→합성). "
            "비교 분석·찬반·복잡한 결정에 최적. 스트리밍 지원 (30~60초)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "토론 주제"}},
            "required": ["query"],
        },
    },
    {
        "name": "quick_answer",
        "description": "단일 LLM 빠른 응답 (solo). 사실 확인·번역·요약. 즉시 응답.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "질문"}},
            "required": ["query"],
        },
    },
]


# ── config ────────────────────────────────────────────────────────

def _get_config() -> dict:
    try:
        return load_config()
    except Exception:
        return {
            "llm": {"provider": "anthropic_oauth", "model": "gpt-5-mini"},
            "agents": {
                "agent_a": {"provider": "openai", "model": "gpt-5-mini"},
                "agent_b": {"provider": "anthropic_oauth", "model": "claude-sonnet-4-6"},
            },
            "amp": {"default_mode": "auto", "kg_path": "~/.amp/kg.db"},
        }


# ── SSE 헬퍼 ─────────────────────────────────────────────────────

def _sse_event(data: dict) -> str:
    """SSE 이벤트 포맷: data: {json}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _rpc_error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _rpc_result(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


# ── 스트리밍 생성기 ────────────────────────────────────────────────

async def _stream_emergent(id_: Any, query: str, rounds: int) -> AsyncGenerator[str, None]:
    """emergent 모드 SSE 스트리밍. 진행 상황 → 최종 결과."""
    config = _get_config()

    # 진행 알림 이벤트
    async def progress(msg: str):
        yield _sse_event({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {"message": msg},
        })

    try:
        async for chunk in progress("🔍 Agent A 독립 분석 중..."):
            yield chunk

        # emergent.run은 동기 함수 → asyncio 스레드풀 실행
        # rounds=2: 병렬화로 ~30s, rounds=4: ~60s → timeout을 여유있게 설정
        mcp_timeout = 120 if rounds == 2 else 180
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: emergent.run(query=query, context=[], config=config, rounds=rounds),
            ),
            timeout=mcp_timeout,
        )

        async for chunk in progress("✅ 분석 완료. 결과 합성 중..."):
            yield chunk

        content = _format_emergent_result(result)
        final = _rpc_result(id_, {"content": [{"type": "text", "text": content}]})
        yield _sse_event(final)

    except asyncio.TimeoutError:
        logger.error("emergent timeout")
        yield _sse_event(_rpc_error(id_, -32000, "분석 시간 초과 (180s). 잠시 후 다시 시도하세요."))
    except Exception as e:
        logger.exception("emergent 스트리밍 오류")
        yield _sse_event(_rpc_error(id_, -32000, str(e)[:200]))


def _cser_label(cser: float) -> str:
    """CSER 점수 → 사람이 이해하기 쉬운 한국어 텍스트"""
    if cser < 0.30:
        return "⚠️ 비슷한 의견 → 심화 분석 진행"
    elif cser < 0.60:
        return "✅ 적절히 다른 시각"
    elif cser < 0.80:
        return "✅ 꽤 다른 시각"
    else:
        return "🔥 매우 다른 시각"


def _format_emergent_result(result: dict) -> str:
    answer = result.get("answer", "")
    cser = result.get("cser")
    rounds = result.get("rounds", 2)
    agent_a_label = result.get("agent_a_label", "Agent A")
    agent_b_label = result.get("agent_b_label", "Agent B")

    lines = [answer]
    if cser is not None:
        label = _cser_label(cser)
        lines.append(f"\n📊 두 AI 시각 다양성: {label} | {cser:.2f} | {rounds}-round")
        lines.append(f"🤖 {agent_a_label} × {agent_b_label}")
    agreements = result.get("agreements", [])
    if agreements:
        lines.append(f"💡 합의점: {', '.join(agreements[:2])}")
    return "\n".join(lines)


# ── 도구 디스패처 ─────────────────────────────────────────────────

async def _dispatch(id_: Any, tool_name: str, arguments: dict, want_stream: bool):
    """
    want_stream=True  → AsyncGenerator (SSE)
    want_stream=False → dict (plain JSON)
    """
    query = arguments.get("query", "").strip()
    if not query:
        err = _rpc_error(id_, -32602, "query 파라미터 필수")
        if want_stream:
            async def _err_gen():
                yield _sse_event(err)
            return _err_gen()
        return err

    if tool_name in ("analyze", "debate"):
        rounds = 4 if tool_name == "debate" else 2
        if want_stream:
            return _stream_emergent(id_, query, rounds)
        # 스트리밍 불가 클라이언트: 동기 실행 후 일반 JSON
        try:
            config = _get_config()
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: emergent.run(query=query, context=[], config=config, rounds=rounds),
            )
            content = _format_emergent_result(result)
            return _rpc_result(id_, {"content": [{"type": "text", "text": content}]})
        except Exception as e:
            return _rpc_error(id_, -32000, str(e)[:200])

    elif tool_name == "quick_answer":
        try:
            config = _get_config()
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: solo.run(query=query, context=[], config=config),
            )
            content = result.get("answer", "")
            resp = _rpc_result(id_, {"content": [{"type": "text", "text": content}]})
            if want_stream:
                async def _quick_gen():
                    yield _sse_event(resp)
                return _quick_gen()
            return resp
        except Exception as e:
            return _rpc_error(id_, -32000, str(e)[:200])

    else:
        err = _rpc_error(id_, -32601, f"알 수 없는 도구: {tool_name}")
        if want_stream:
            async def _unknown_gen():
                yield _sse_event(err)
            return _unknown_gen()
        return err


# ── FastAPI 라우트 ────────────────────────────────────────────────

@app.post("/")
async def handle_rpc(request: Request):
    """
    MCP Streamable HTTP 엔드포인트.
    Accept: text/event-stream → SSE 스트리밍
    Accept: application/json  → 일반 JSON (기본)
    """
    # ── 요청 파싱 ──
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "JSON 파싱 오류"))

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # ── 스트리밍 여부 판단 ──
    accept = request.headers.get("accept", "")
    want_stream = "text/event-stream" in accept

    # ── 메서드 라우팅 ──
    if method == "ping":
        result = _rpc_result(rpc_id, {"status": "ok", "service": "amp-mcp"})
        return JSONResponse(result)

    elif method == "tools/list":
        result = _rpc_result(rpc_id, {"tools": TOOLS})
        return JSONResponse(result)

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        dispatched = await _dispatch(rpc_id, tool_name, arguments, want_stream)

        if want_stream and hasattr(dispatched, "__aiter__"):
            return StreamingResponse(
                dispatched,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        return JSONResponse(dispatched)

    else:
        return JSONResponse(_rpc_error(rpc_id, -32601, f"지원하지 않는 메서드: {method}"))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "amp-mcp-server", "version": "2.0.0", "transport": "streamable-http"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[amp-mcp] Streamable HTTP 서버 시작: http://127.0.0.1:3010")
    uvicorn.run(app, host="127.0.0.1", port=3010, log_level="info")
