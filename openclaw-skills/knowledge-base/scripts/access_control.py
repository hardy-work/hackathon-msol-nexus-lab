#!/usr/bin/env python3
"""Fail-closed read authorization for Knowledge Base.

The repository declares policy, but the caller identity and roles must come
from the trusted host process.  Query text and gateway payload fields cannot
grant themselves access.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _csv(value: str) -> frozenset[str]:
    return frozenset(x.strip() for x in value.split(",") if x.strip())


@dataclass(frozen=True)
class AccessContext:
    actor: str
    roles: frozenset[str]

    @classmethod
    def from_runtime(cls, actor: str | None = None,
                     roles: str | None = None) -> "AccessContext":
        return cls(
            (actor if actor is not None else os.getenv("KNOWLEDGE_BASE_ACTOR", "")).strip(),
            _csv(roles if roles is not None else os.getenv("KNOWLEDGE_BASE_ROLES", "")),
        )

    @property
    def fingerprint(self) -> str:
        value = f"{self.actor}\n{','.join(sorted(self.roles))}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def policy(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "access.yml").read_text(encoding="utf-8")) or {}


def authorize_project(ctx: AccessContext, root: Path = ROOT) -> tuple[bool, str]:
    cfg = policy(root)
    visibility = cfg.get("default_visibility", "internal")
    if visibility == "public":
        return True, "public project"
    if not ctx.actor:
        return False, "missing trusted actor identity"
    allowed = set(cfg.get("visibility_roles", {}).get(visibility, []))
    if not (ctx.roles & allowed):
        return False, f"actor has no role allowed for `{visibility}` knowledge"
    return True, "authorized"


def can_read_metadata(ctx: AccessContext, metadata: dict, root: Path = ROOT) -> bool:
    visibility = metadata.get("visibility") or policy(root).get("default_visibility", "internal")
    users = set(metadata.get("allowed_users") or [])
    roles = set(metadata.get("allowed_roles") or [])
    if visibility == "public":
        return True
    if not ctx.actor:
        return False
    if ctx.actor in users or ctx.roles & roles:
        return True
    return bool(ctx.roles & set(policy(root).get("visibility_roles", {}).get(visibility, [])))


def selftest() -> None:
    assert not authorize_project(AccessContext("", frozenset()))[0]
    assert authorize_project(AccessContext("demo", frozenset({"project_member"})))[0]
    assert not authorize_project(AccessContext("outsider", frozenset({"guest"})))[0]
    assert can_read_metadata(AccessContext("pm", frozenset({"project_manager"})),
                             {"visibility": "restricted"})
    print("access_control selftest: OK")


if __name__ == "__main__":
    selftest()
