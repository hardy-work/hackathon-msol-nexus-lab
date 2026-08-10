#!/usr/bin/env python3
"""Long-lived, access-scoped Project Knowledge query engine."""
from __future__ import annotations

import re
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

import access_control
import answer
import document_registry
import filesystem_boundary
import query_cache
import runtime_state
import telemetry
import versioning

ROOT = Path(__file__).resolve().parent.parent


def suggested_actions(query: str, status: str, citations: list[str]) -> list[dict[str, object]]:
    if not (re.search(r"\b(cập nhật|sửa|tạo|đổi|xóa|update|create|delete|remove|add)\b", query, re.I)
            or re.match(r"\s*(ghi|log)\b", query, re.I)):
        return []
    return [{
        "type": "project_action", "status": "proposed", "requires_approval": True,
        "required_permission": "project_action:write", "approval_flow": "external_action_skill",
        "description": "Chuyển yêu cầu ghi/cập nhật sang action skill có permission; Project Knowledge không tự thay đổi dữ liệu.",
        "request": query, "context_status": status, "context_citations": list(citations),
    }]


class KnowledgeRuntime:
    """Reuse DuckDB/graph/vector state while isolating KB views by access fingerprint."""

    def __init__(self, root: Path = ROOT, max_access_views: int = 32):
        self.boundary = filesystem_boundary.ReadOnlyCorpus(root)
        self.boundary.assert_safe()
        self.root = self.boundary.root
        # Cache is operational state, not corpus.  It may be writable, but it
        # must never overlap an input or derived index directory.
        self.state_dir = self.boundary.assert_state_separate(runtime_state.state_dir(self.root))
        self.max_access_views = max_access_views
        self._lock = threading.RLock()
        self._views: OrderedDict[tuple[str, str], answer.KB] = OrderedDict()
        self._corpus_token: str | None = None
        self._last_version_check = 0.0
        self._cache: query_cache.QueryCache | None = None

    def _token(self) -> str:
        interval = max(0.1, float(os.getenv("PROJECT_KNOWLEDGE_VERSION_CHECK_SECONDS", "5")))
        now = time.monotonic()
        if self._corpus_token is not None and now - self._last_version_check < interval:
            return self._corpus_token
        state = versioning.check(self.root)
        self._last_version_check = now
        return str(state.get("current_input_sha256") or state.get("input_sha256")
                   or state.get("version") or "unknown")

    def _view(self, access: access_control.AccessContext) -> tuple[answer.KB, str]:
        token = self._token()
        if token != self._corpus_token:
            for kb in self._views.values():
                try:
                    kb.con.close()
                except Exception:
                    pass
            self._views.clear()
            self._corpus_token = token
            # Derived graph/vector files may have changed with the corpus.
            answer.reset_indexes()
            answer.numeric_guard.reset(self.root)
        key = (access.fingerprint, token)
        kb = self._views.get(key)
        if kb is None:
            kb = answer.KB(root=self.root, access=access, boundary=self.boundary)
            self._views[key] = kb
            while len(self._views) > self.max_access_views:
                _, old = self._views.popitem(last=False)
                old.con.close()
        else:
            self._views.move_to_end(key)
        return kb, token

    def reload(self) -> None:
        """Drop corpus-bound state after an atomic publish.

        The normal query path already detects a changed corpus digest lazily.
        NexusBot/deployment code can call this explicit hook immediately after
        publishing a new approved corpus version, avoiding a window where a
        long-lived process still holds old DuckDB/graph/vector views.
        """
        with self._lock:
            for kb in self._views.values():
                try:
                    kb.con.close()
                except Exception:
                    pass
            self._views.clear()
            self._corpus_token = None
            self._last_version_check = 0.0
            answer.reset_indexes()
            answer.numeric_guard.reset(self.root)

    def query(self, project: str, question: str, *, llm: bool = False,
              actor: str | None = None, roles: str | list[str] | None = None,
              history: list[dict] | None = None, use_cache: bool = True) -> dict:
        started = time.perf_counter()
        history = history or []
        role_text = ",".join(roles) if isinstance(roles, list) else roles
        access = access_control.AccessContext.from_runtime(actor, role_text)
        qhash = telemetry.question_hash(question)

        def finish(payload: dict) -> dict:
            telemetry.record(
                "query", project=project, status=payload.get("status"),
                tier=payload.get("tier", 0), cache_hit=payload.get("cache_hit", False),
                route=(payload.get("route") or {}).get("name"),
                access_fingerprint=access.fingerprint, question_hash=qhash,
                knowledge_version=payload.get("knowledge_version"),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            return payload

        if project.lower() != "nexus":
            return finish({"status": "error", "answer": "Demo hiện chỉ hỗ trợ project nexus.",
                           "confidence": "none", "citations": [],
                           "reason": "project chưa có corpus hoặc adapter tương ứng.",
                           "tier": 0, "project": project, "suggested_actions": []})
        allowed, reason = access_control.authorize_project(access, self.root)
        if not allowed:
            return finish({"status": "forbidden",
                           "answer": "Bạn không có quyền đọc Project Knowledge của dự án này.",
                           "confidence": "none", "citations": [], "reason": reason,
                           "tier": 0, "project": project, "suggested_actions": []})
        if not versioning.indexes_ready(self.root):
            return finish({
                "status": "error",
                "answer": "Kho truy vấn chưa sẵn sàng.",
                "confidence": "none",
                "citations": [],
                "reason": "Thiếu hoặc stale BM25/Chroma index; chạy scripts/build_rag_indexes.py "
                          "sau đó chạy scripts/versioning.py build.",
                "tier": 0,
                "project": project,
                "suggested_actions": [],
            })
        if not isinstance(history, list):
            return finish({"status": "error", "answer": "Conversation history không hợp lệ.",
                           "confidence": "none", "citations": [], "reason": "history must be a list",
                           "tier": 0, "project": project, "suggested_actions": []})

        try:
            with self._lock:
                kb, token = self._view(access)
                effective = question
                previous = next((m for m in reversed(history)
                                 if m.get("role") == "user" and m.get("content")), None)
                if previous:
                    people = kb.find_people(previous["content"])
                    slug = people[0] if len(people) == 1 else None
                    effective = answer.resolve_ellipsis(
                        kb, question, previous["content"], slug) or question

                key = query_cache.cache_key(project, effective, token, access.fingerprint, llm, history)
                if self._cache is None:
                    self._cache = query_cache.QueryCache(self.state_dir / "query_cache.sqlite3")
                cache = self._cache
                cached = cache.get(key) if use_cache else None
                if cached is not None:
                    cached["cache_hit"] = True
                    if effective != question:
                        cached["effective_query"] = effective
                    return finish(cached)

                result = answer.ask(kb, effective, llm=llm)
                status = {answer.CO: "in_kb", answer.NO: "confident_no",
                          answer.NF: "not_in_kb"}.get(result.outcome, "error")
                confidence = {"in_kb": "high" if result.tier == 1 else "medium",
                              "confident_no": "high", "not_in_kb": "none",
                              "error": "none"}[status]
                display_citations = document_registry.public_citations(result.cites, self.root)
                payload = {"status": status, "answer": result.answer,
                           "confidence": confidence, "citations": display_citations,
                           "reason": result.reason, "tier": result.tier, "project": project,
                           "suggested_actions": suggested_actions(question, status, display_citations),
                           "cache_hit": False}
                payload["answer"] = answer.public_answer(self.root, payload["answer"])
                freshness = getattr(kb, "freshness", None)
                if freshness is not None:
                    payload.update({"freshness": freshness,
                                    "knowledge_version": freshness.get("version"),
                                    "knowledge_as_of": freshness.get("as_of")})
                    if freshness.get("state") != "fresh":
                        payload["reason"] = (payload["reason"] +
                            " Dữ liệu dẫn xuất chưa được xác nhận fresh; hãy chạy scripts/run_all.sh.").strip()
                if result.route is not None:
                    payload["route"] = {"name": result.route.route,
                                        "confidence": result.route.confidence,
                                        "source": result.route.source,
                                        "reason": result.route.reason}
                    if result.route.error:
                        payload["route"]["error"] = result.route.error
                if effective != question:
                    payload["effective_query"] = effective
                if use_cache and status != "error":
                    cache.put(key, token, payload)
                return finish(payload)
        except Exception as exc:
            return finish({"status": "error", "answer": "Không thể truy vấn project knowledge.",
                           "confidence": "none", "citations": [],
                           "reason": f"{type(exc).__name__}: {exc}", "tier": 0,
                           "project": project, "suggested_actions": []})


_runtime: KnowledgeRuntime | None = None
_runtime_lock = threading.Lock()


def default_runtime() -> KnowledgeRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = KnowledgeRuntime()
        return _runtime
