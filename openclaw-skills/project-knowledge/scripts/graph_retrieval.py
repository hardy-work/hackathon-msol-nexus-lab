#!/usr/bin/env python3
"""Small, provenance-preserving graph retrieval layer for Nexus.

The graph is a derived index, not a new source of truth.  Every task result
keeps its source cell so Graph retrieval can narrow multi-hop context without
inventing dependencies that are absent from the workbook.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import access_control


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


@dataclass(frozen=True)
class GraphHit:
    task_id: str
    name: str
    assignee: str | None
    role: str | None
    category: str | None
    status: str | None
    priority: str | None
    source: str | None


@dataclass(frozen=True)
class GraphAnswer:
    answer: str
    citations: tuple[str, ...]
    reason: str


def is_relation_query(query: str) -> bool:
    """Detect graph-shaped wording without making a semantic claim."""
    q = normalize(query)
    return bool(re.search(
        r"thuoc|lien quan|phu thuoc|phu trach cac|anh huong|blocked|dependency|"
        r"milestone|module|category|quan he|tac dong|danh sach task",
        q,
    ))


class GraphIndex:
    def __init__(self, root: Path):
        self.root = root
        path = root / "derived" / "graph.json"
        self.graph: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.nodes = {node["id"]: node for node in self.graph.get("nodes", [])}
        self.edges = self.graph.get("edges", [])
        self.out: dict[str, list[dict[str, Any]]] = {}
        self.inc: dict[str, list[dict[str, Any]]] = {}
        for edge in self.edges:
            self.out.setdefault(edge["from"], []).append(edge)
            self.inc.setdefault(edge["to"], []).append(edge)
        self.tasks = [n for n in self.nodes.values() if n.get("type") == "task"]
        self.dimensions = [n for n in self.nodes.values() if n.get("type") == "dimension"]

    @property
    def available(self) -> bool:
        return bool(self.tasks)

    def _dimension_ids(self, query: str) -> set[str]:
        q = normalize(query)
        found: set[str] = set()
        for node in self.dimensions:
            value = normalize(node.get("value", ""))
            if not value:
                continue
            if len(value) <= 2:
                if re.search(rf"\b{re.escape(value)}\b", q):
                    found.add(node["id"])
            elif value in q:
                found.add(node["id"])
        return found

    def _can_read(self, node: dict[str, Any], access) -> bool:
        return access is None or access_control.can_read_metadata(access, node, self.root)

    def _people_in_query(self, query: str, access=None) -> set[str]:
        q = normalize(query)
        return {node["id"] for node in self.nodes.values()
                if node.get("type") == "entity-person" and self._can_read(node, access)
                and normalize(node.get("name")) in q}

    def _task_hit(self, node: dict[str, Any]) -> GraphHit:
        values = {e["rel"]: self.nodes.get(e["to"], {}) for e in self.out.get(node["id"], [])}
        # A task has at most one target for each relation in the current corpus.
        assigned = values.get("assigned_to", {})
        role = values.get("has_role", {})
        category = values.get("in_milestone", {})
        status = values.get("has_status", {})
        priority = values.get("has_priority", {})
        source = node.get("source")
        return GraphHit(
            task_id=str(node.get("task_id", node["id"])),
            name=str(node.get("name", node["id"])),
            assignee=assigned.get("name") or assigned.get("value"),
            role=role.get("value"),
            category=category.get("value"),
            status=status.get("value"),
            priority=priority.get("value"),
            source=source,
        )

    def task_hits(self, query: str, limit: int = 60, access=None) -> list[GraphHit]:
        q = normalize(query)
        dimensions = self._dimension_ids(query)
        people = self._people_in_query(query, access)
        explicit_ids = {normalize(match) for match in re.findall(r"[A-Za-z]+-\d+", query)}
        hits: list[GraphHit] = []
        for node in self.tasks:
            if not self._can_read(node, access):
                continue
            outgoing = self.out.get(node["id"], [])
            targets = {e["to"] for e in outgoing}
            task_id = normalize(node.get("task_id", ""))
            task_name = normalize(node.get("name", ""))
            selector = False
            matches = True
            if dimensions:
                selector = True
                # Every mentioned dimension must match the same task.
                matches = matches and dimensions.issubset(targets)
            if people:
                selector = True
                matches = matches and any(
                    e["to"] in people for e in outgoing if e["rel"] == "assigned_to"
                )
            if explicit_ids:
                selector = True
                matches = matches and task_id in explicit_ids
            name_terms = [term for term in re.findall(r"[a-z0-9]+", q)
                          if len(term) > 3 and term not in {"task", "tasks", "cong", "viec", "nhung", "nao"}]
            if not selector and name_terms:
                overlap = sum(term in task_name for term in name_terms)
                if overlap:
                    selector = True
                    matches = overlap >= max(1, min(2, len(name_terms)))
            if selector and matches:
                hits.append(self._task_hit(node))
        return hits[:limit]

    def context(self, query: str, limit: int = 12, access=None) -> tuple[str, tuple[str, ...]]:
        hits = self.task_hits(query, limit=limit, access=access)
        if not hits:
            return "", ()
        lines = []
        citations = {"raw/nexus-sprint1.facts.json"}
        for hit in hits:
            lines.append(
                f"task={hit.task_id}; name={hit.name}; assignee={hit.assignee or '—'}; "
                f"role={hit.role or '—'}; category={hit.category or '—'}; "
                f"status={hit.status or '—'}; priority={hit.priority or '—'}; "
                f"source={hit.source or 'unknown'}"
            )
            if hit.source:
                citations.add(hit.source)
        return "\n".join(lines), tuple(sorted(citations))

    def direct_answer(self, query: str, access=None) -> GraphAnswer | None:
        hits = self.task_hits(query, access=access)
        if not hits:
            return None
        q = normalize(query)
        asks_people = bool(re.search(r"\b(ai|nguoi|assignee|phu trach)\b", q))
        asks_tasks = bool(re.search(r"\b(task|tasks|cong viec|dau viec)\b", q))
        asks_roles = bool(re.search(r"\b(role|vai tro)\b", q))
        asks_list = bool(re.search(r"\b(nhung|nao|liet ke|danh sach|cac)\b", q))
        if not (asks_people or asks_tasks or asks_roles) or not asks_list:
            return None

        if asks_people:
            values = sorted({h.assignee for h in hits if h.assignee})
            if values:
                answer = "Những người liên quan: " + ", ".join(f"**{value}**" for value in values) + "."
            else:
                return None
        elif asks_roles:
            values = sorted({h.role for h in hits if h.role})
            if values:
                answer = "Các vai trò liên quan: " + ", ".join(f"`{value}`" for value in values) + "."
            else:
                return None
        else:
            grouped: dict[str, list[str]] = {}
            for hit in hits:
                grouped.setdefault(hit.assignee or "chưa gán", []).append(
                    f"{hit.task_id} — {hit.name}"
                )
            rows = [f"**{person}**: " + "; ".join(tasks)
                    for person, tasks in sorted(grouped.items())]
            answer = "\n".join(rows)
        cites = tuple(sorted({"raw/nexus-sprint1.facts.json", *(h.source for h in hits if h.source)}))
        return GraphAnswer(answer, cites,
                           "graph retrieval nối task với assignee/role/milestone/status từ facts có provenance.")


def load(root: Path) -> GraphIndex | None:
    try:
        index = GraphIndex(root)
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    return index if index.available else None
