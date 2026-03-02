"""Knowledge Graph - JSON-based local knowledge store.

Stores insights, facts, and relationships as nodes and edges.
All data stays local at ~/.amp/kg.json.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class KnowledgeGraph:
    """Simple JSON-backed knowledge graph."""

    def __init__(self, path: str | Path = "~/.amp/kg.json"):
        self.path = Path(path).expanduser()
        self._data: dict = {"nodes": [], "edges": []}
        self._load()

    def _load(self) -> None:
        """Load graph from disk, create empty if not exists."""
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
                # Ensure structure
                self._data.setdefault("nodes", [])
                self._data.setdefault("edges", [])
            except (json.JSONDecodeError, OSError):
                self._data = {"nodes": [], "edges": []}

    def _save(self) -> None:
        """Persist graph to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add(self, content: str, tags: list[str] | None = None) -> str:
        """Add a node to the graph.

        Returns:
            str: Node ID
        """
        node_id = str(uuid.uuid4())[:8]
        node = {
            "id": node_id,
            "content": content,
            "tags": tags or [],
            "created": datetime.now().isoformat(),
        }
        self._data["nodes"].append(node)
        self._save()
        return node_id

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Keyword-based search over nodes.

        Returns top_k nodes sorted by relevance (keyword hit count).
        """
        query_words = set(re.findall(r"\b\w{2,}\b", query.lower()))
        if not query_words:
            return self._data["nodes"][:top_k]

        scored = []
        for node in self._data["nodes"]:
            text = (node["content"] + " " + " ".join(node["tags"])).lower()
            node_words = set(re.findall(r"\b\w{2,}\b", text))
            score = len(query_words & node_words)
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored[:top_k]]

    def relate(self, node_a: str, node_b: str, relation: str) -> None:
        """Create a directed edge between two nodes."""
        # Validate nodes exist
        node_ids = {n["id"] for n in self._data["nodes"]}
        if node_a not in node_ids or node_b not in node_ids:
            raise ValueError(f"Node(s) not found: {node_a}, {node_b}")

        edge = {
            "from": node_a,
            "to": node_b,
            "relation": relation,
            "created": datetime.now().isoformat(),
        }
        self._data["edges"].append(edge)
        self._save()

    def get_node(self, node_id: str) -> dict | None:
        """Get a node by ID."""
        for node in self._data["nodes"]:
            if node["id"] == node_id:
                return node
        return None

    def stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        return {
            "node_count": len(self._data["nodes"]),
            "edge_count": len(self._data["edges"]),
            "tags": list({tag for n in self._data["nodes"] for tag in n["tags"]}),
        }

    def recent(self, n: int = 5) -> list[dict]:
        """Return most recently added nodes."""
        return sorted(
            self._data["nodes"],
            key=lambda x: x.get("created", ""),
            reverse=True,
        )[:n]
