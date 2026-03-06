"""
amp Dynamic Domain Registry
쿼리가 쌓일수록 도메인 풀이 자동으로 성장한다.

흐름:
  1. 키워드 매칭 (정적, O(1))           → hit: 기존 preset 사용
  2. 임베딩 유사도 탐색 (SQLite)         → hit (≥0.82): 캐시된 도메인 재사용
  3. LLM 도메인 창작 (gpt-5-mini 1회)   → 새 도메인 생성 + 저장
     └→ 유사 도메인 병합 체크 (≥0.75)  → 중복 방지
"""

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ─── 유사도 임계값 ────────────────────────────────────────────────────────────
REUSE_THRESHOLD  = 0.78   # 이 이상이면 캐시된 도메인 그대로 재사용
MERGE_THRESHOLD  = 0.75   # 신규 도메인 생성 시, 이 이상이면 기존 도메인으로 병합

EMBEDDING_MODEL  = "text-embedding-3-small"
DOMAIN_LLM_MODEL = "gpt-5-mini"


@dataclass
class DomainSpec:
    name: str
    persona_a: str
    persona_b: str
    sv_persona_a: str    # same-vendor 극단 버전
    sv_persona_b: str    # same-vendor 극단 버전
    keywords: list[str]
    source: str          # "cached" | "created" | "merged"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x**2 for x in a) ** 0.5
    nb = sum(x**2 for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class DomainRegistry:
    """
    동적 도메인 레지스트리 — SQLite 기반.

    amp의 KG DB(~/.amp/kg.db)에 `domains` 테이블을 추가해서 사용.
    domain_registry 전용 DB를 분리하지 않고 KG와 같은 파일에 저장
    → 단일 DB 파일로 관리 단순화.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.amp/kg.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ─── DB 초기화 ────────────────────────────────────────────────────────────

    def _init_schema(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domains (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT    UNIQUE NOT NULL,
                    keywords     TEXT    DEFAULT '[]',
                    persona_a    TEXT    NOT NULL,
                    persona_b    TEXT    NOT NULL,
                    sv_persona_a TEXT    NOT NULL,
                    sv_persona_b TEXT    NOT NULL,
                    embedding    TEXT,
                    usage_count  INTEGER DEFAULT 0,
                    created_at   REAL    DEFAULT (unixepoch())
                )
            """)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ─── 공개 API ─────────────────────────────────────────────────────────────

    def find(self, query: str, client) -> Optional[DomainSpec]:
        """
        쿼리와 가장 유사한 기존 도메인을 반환.
        임계값 미달이면 None 반환 → 신규 생성 필요.
        """
        try:
            from openai import OpenAI  # lazy import
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[query],
            )
            query_emb = resp.data[0].embedding
        except Exception:
            return None

        rows = self._fetch_domains_with_embeddings()
        if not rows:
            return None

        best_score = -1.0
        best_row = None
        for row in rows:
            emb = json.loads(row["embedding"])
            score = _cosine(query_emb, emb)
            if score > best_score:
                best_score = score
                best_row = row

        if best_row and best_score >= REUSE_THRESHOLD:
            self._bump_usage(best_row["name"])
            return DomainSpec(
                name=best_row["name"],
                persona_a=best_row["persona_a"],
                persona_b=best_row["persona_b"],
                sv_persona_a=best_row["sv_persona_a"],
                sv_persona_b=best_row["sv_persona_b"],
                keywords=json.loads(best_row["keywords"]),
                source="cached",
            )
        return None

    def create(self, query: str, client) -> DomainSpec:
        """
        LLM을 호출해 새 도메인을 창작한다.
        유사 도메인이 있으면 병합 후 반환.
        항상 DomainSpec을 반환한다 (실패 시 'general' 폴백).
        """
        data = self._llm_create_domain(query, client)
        embedding = self._embed_domain(data, client)

        # 병합 체크: 기존 도메인과 너무 가까우면 신규 생성 대신 기존 반환
        if embedding:
            merged = self._try_merge(embedding)
            if merged:
                return merged

        # 신규 저장
        return self._save_domain(data, embedding)

    def list_all(self) -> list[dict]:
        """등록된 모든 동적 도메인 목록."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name, keywords, usage_count, created_at "
                "FROM domains ORDER BY usage_count DESC"
            ).fetchall()
        return [
            {
                "name": row[0],
                "keywords": json.loads(row[1]),
                "usage_count": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]

    # ─── 내부 헬퍼 ───────────────────────────────────────────────────────────

    def _fetch_domains_with_embeddings(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name, persona_a, persona_b, sv_persona_a, sv_persona_b, "
                "keywords, embedding FROM domains WHERE embedding IS NOT NULL"
            ).fetchall()
        return [
            {
                "name": r[0], "persona_a": r[1], "persona_b": r[2],
                "sv_persona_a": r[3], "sv_persona_b": r[4],
                "keywords": r[5], "embedding": r[6],
            }
            for r in rows
        ]

    def _bump_usage(self, name: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE domains SET usage_count = usage_count + 1 WHERE name = ?",
                (name,),
            )
            conn.commit()

    def _llm_create_domain(self, query: str, client) -> dict:
        """gpt-5-mini로 도메인명 + 페르소나 쌍 동시 생성."""
        system = (
            "You are a domain classification expert. "
            "Given a query, define a new reasoning domain. "
            "Return ONLY valid JSON, no markdown."
        )
        user = f"""Query: {query}

Create a domain specification:
{{
  "name": "short_snake_case_id (e.g. forensics, philosophy, urban_planning)",
  "keywords": ["5-10 keywords matching this domain, in the query's language"],
  "persona_a": "Expert persona A — analytical / precision framing",
  "persona_b": "Expert persona B — genuinely contrasting framing",
  "sv_persona_a": "EXTREME version of A for same-vendor divergence (push to the limit)",
  "sv_persona_b": "EXTREME version of B for same-vendor divergence (push to the limit)"
}}"""
        _FALLBACK = {
            "name": "general",
            "keywords": [],
            "persona_a": "분석적 전문가 — 논리, 증거, 측정 가능한 결론",
            "persona_b": "공감적 조언자 — 맥락, 감정, 가치 중심",
            "sv_persona_a": "정밀 분석가 — 수치, 재현성, 불확실성 최소화",
            "sv_persona_b": "직관적 통합자 — 시스템 패턴, 감정 신호, 전체론적 판단",
        }
        try:
            resp = client.chat.completions.create(
                model=DOMAIN_LLM_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_completion_tokens=4000,
                
            )
            data = json.loads(resp.choices[0].message.content)
            # 필수 키 검증
            for key in ("name", "persona_a", "persona_b"):
                if key not in data:
                    return _FALLBACK
            return data
        except Exception:
            return _FALLBACK

    def _embed_domain(self, data: dict, client) -> Optional[list[float]]:
        """도메인명 + 키워드를 임베딩해서 반환."""
        try:
            text = data["name"] + " " + " ".join(data.get("keywords", []))
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[text],
            )
            return resp.data[0].embedding
        except Exception:
            return None

    def _try_merge(self, new_embedding: list[float]) -> Optional[DomainSpec]:
        """새 임베딩이 기존 도메인과 MERGE_THRESHOLD 이상 유사하면 병합."""
        rows = self._fetch_domains_with_embeddings()
        for row in rows:
            existing_emb = json.loads(row["embedding"])
            if _cosine(new_embedding, existing_emb) >= MERGE_THRESHOLD:
                self._bump_usage(row["name"])
                return DomainSpec(
                    name=row["name"],
                    persona_a=row["persona_a"],
                    persona_b=row["persona_b"],
                    sv_persona_a=row["sv_persona_a"],
                    sv_persona_b=row["sv_persona_b"],
                    keywords=json.loads(row["keywords"]),
                    source="merged",
                )
        return None

    def _save_domain(self, data: dict, embedding: Optional[list[float]]) -> DomainSpec:
        """신규 도메인을 DB에 저장하고 DomainSpec 반환."""
        name = data.get("name", "unknown").lower().replace(" ", "_")[:48]
        spec = DomainSpec(
            name=name,
            persona_a=data.get("persona_a", "분석적 전문가"),
            persona_b=data.get("persona_b", "공감적 조언자"),
            sv_persona_a=data.get("sv_persona_a", data.get("persona_a", "정밀 분석가")),
            sv_persona_b=data.get("sv_persona_b", data.get("persona_b", "직관적 통합자")),
            keywords=data.get("keywords", []),
            source="created",
        )
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO domains
                       (name, keywords, persona_a, persona_b, sv_persona_a, sv_persona_b, embedding)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        spec.name,
                        json.dumps(spec.keywords, ensure_ascii=False),
                        spec.persona_a,
                        spec.persona_b,
                        spec.sv_persona_a,
                        spec.sv_persona_b,
                        json.dumps(embedding) if embedding else None,
                    ),
                )
                conn.commit()
        except Exception:
            pass
        return spec
