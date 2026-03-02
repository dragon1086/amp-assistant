"""
amp Knowledge Graph — SQLite + OpenAI text-embedding-3-small
Designed with cokac-bot. Lightweight, precise, extensible.

Storage: SQLite (nodes + edges + embeddings as JSON blobs)
Search: numpy cosine similarity (flat, sufficient for <100k nodes)
Embeddings: OpenAI text-embedding-3-small via EmbeddingAdapter pattern
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

KG_DIR = Path.home() / ".amp"
DB_PATH = KG_DIR / "kg.db"


class EmbeddingAdapter:
    """Adapter pattern: swap OpenAI for local model later."""

    def __init__(self, provider="openai"):
        self.provider = provider

    def embed(self, text: str) -> list[float]:
        if self.provider == "openai":
            return self._openai_embed(text)
        raise NotImplementedError(f"Provider {self.provider} not supported yet")

    def _openai_embed(self, text: str) -> list[float]:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],  # safe truncation
        )
        return response.data[0].embedding


class KnowledgeGraph:
    """
    Local knowledge graph backed by SQLite.
    Semantic search via OpenAI embeddings + numpy cosine similarity (flat).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = EmbeddingAdapter(provider="openai")
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT DEFAULT 'insight',
                content TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                embedding TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            );
        """)
        # Migrate existing DBs that lack the embedding column
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(nodes)")}
        if "embedding" not in cols:
            self.conn.execute("ALTER TABLE nodes ADD COLUMN embedding TEXT DEFAULT NULL")
        self.conn.commit()

    def add(self, content: str, tags: list = None, node_type: str = "insight", metadata: dict = None) -> str:
        """Add a node to the KG. Returns node id."""
        node_id = str(uuid.uuid4())[:8]
        tags = tags or []
        metadata = metadata or {}

        embedding = self.embedder.embed(content)

        self.conn.execute(
            "INSERT INTO nodes (id, type, content, tags, metadata, embedding, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                node_id,
                node_type,
                content,
                json.dumps(tags),
                json.dumps(metadata),
                json.dumps(embedding),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()
        return node_id

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search via cosine similarity. Returns top-k relevant nodes."""
        try:
            query_vec = np.array(self.embedder.embed(query), dtype=np.float32)
        except Exception:
            return []

        rows = self.conn.execute(
            "SELECT id, type, content, tags, embedding FROM nodes WHERE embedding IS NOT NULL"
        ).fetchall()

        if not rows:
            return []

        scored = []
        for row in rows:
            vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
            # Cosine similarity
            norm = np.linalg.norm(query_vec) * np.linalg.norm(vec)
            similarity = float(np.dot(query_vec, vec) / norm) if norm > 0 else 0.0
            scored.append((similarity, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "tags": json.loads(row["tags"]),
                "type": row["type"],
                "similarity": sim,
            }
            for sim, row in scored[:top_k]
        ]

    def relate(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> str:
        """Create an edge between two nodes."""
        edge_id = str(uuid.uuid4())[:8]
        self.conn.execute(
            "INSERT INTO edges (id, source_id, target_id, relation, weight, created_at) VALUES (?,?,?,?,?,?)",
            (edge_id, source_id, target_id, relation, weight, datetime.now().isoformat()),
        )
        self.conn.commit()
        return edge_id

    def stats(self) -> dict:
        node_count = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"nodes": node_count, "edges": edge_count, "db_path": str(self.db_path)}

    def migrate_from_json(self, json_path: str):
        """Migrate old JSON KG to new SQLite format."""
        with open(json_path) as f:
            old = json.load(f)
        nodes = old.get("nodes", [])
        print(f"Migrating {len(nodes)} nodes...")
        for node in nodes:
            self.add(
                content=node.get("content", ""),
                tags=node.get("tags", []),
                node_type=node.get("type", "insight"),
                metadata=node.get("metadata", {}),
            )
        print(f"✅ Migration complete: {len(nodes)} nodes migrated")
