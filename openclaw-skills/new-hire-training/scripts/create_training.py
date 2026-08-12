#!/usr/bin/env python3
"""Build a provenance-first new-hire training handbook from knowledge-base wiki pages."""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml


ALLOWED_VISIBILITY = {"public", "internal"}
SKIP_NAMES = {"index.md", "log.md", ".gitkeep"}
AREA_NAMES = ("sources", "entities", "concepts", "case-studies")


# These profiles change the learning path and explicitly expose missing
# role-specific material.  They are not policy claims: the generator keeps
# them labelled as gaps/suggested activities so it never invents a workflow.
ROLE_PROFILES = {
    "developer": {
        "label": "Developer / Engineering",
        "title": "Trọng tâm Developer và chuẩn bị nhận task",
        "outcome": "Biết truy nguồn task/team của Nexus và nhận diện phần setup kỹ thuật cần xác nhận với Tech Lead.",
        "activity": "Đề xuất: chọn một task trong KB, truy owner/status/source rồi lập checklist câu hỏi về repository và môi trường.",
        "first_activity": "Đề xuất: trace một task từ nguồn đến owner/status, sau đó ghi rõ các bước kỹ thuật chưa có nguồn.",
        "gaps": [
            "quy trình setup máy, repository và kiến trúc module",
            "branch/PR, code review, CI/CD và coding convention",
            "tech-stack và tiêu chí kiểm thử cho vai trò cụ thể",
        ],
        "questions": [
            "Repository, kiến trúc module và cách setup môi trường Developer? — `[Chưa có trong KB]`",
            "Quy ước branch/PR, code review và CI/CD? — `[Chưa có trong KB]`",
        ],
    },
    "qa": {
        "label": "QA / Quality Assurance",
        "title": "Trọng tâm QA và chuẩn bị kiểm thử",
        "outcome": "Biết truy context dự án/team và phân biệt dữ liệu đã có với quy trình QA cần hỏi lại.",
        "activity": "Đề xuất: chọn một task, lập danh sách câu hỏi về acceptance criteria, môi trường và nguồn kết quả kiểm thử.",
        "first_activity": "Đề xuất: trace một task từ nguồn đến status, đánh dấu các tiêu chí kiểm thử chưa được KB công bố.",
        "gaps": [
            "test strategy, test case và tiêu chí pass/fail",
            "môi trường test, dữ liệu test và quy trình quản lý defect",
            "release criteria, regression và đầu mối QA",
        ],
        "questions": [
            "Test strategy, môi trường test và quy trình defect của Nexus? — `[Chưa có trong KB]`",
            "Tiêu chí release/regression và đầu mối QA? — `[Chưa có trong KB]`",
        ],
    },
    "project-manager": {
        "label": "Project Manager",
        "title": "Trọng tâm PM và điều phối dự án",
        "outcome": "Biết các nguồn resource, schedule, sprint, risk, issue của Nexus và nhận diện quy trình điều phối còn thiếu.",
        "activity": "Đề xuất: mở Nexus Plan, trace một risk/issue/task về nguồn rồi ghi câu hỏi cần xác nhận với PM/owner.",
        "first_activity": "Đề xuất: chọn một risk hoặc task, xác định nguồn và chuẩn bị câu hỏi về owner, status, escalation.",
        "gaps": [
            "quy trình Jira/Slack để log task, update và log time",
            "mẫu daily report, meeting follow-up và cadence báo cáo",
            "quyền owner/escalation và quy trình xử lý risk/issue",
        ],
        "questions": [
            "Quy trình Jira/Slack, daily report và log time chính thức? — `[Chưa có trong KB]`",
            "Ai phê duyệt escalation risk/issue và theo cadence nào? — `[Chưa có trong KB]`",
        ],
    },
    "hr-operations": {
        "label": "HR / Operations",
        "title": "Trọng tâm HR/Operations và tuân thủ nội bộ",
        "outcome": "Nắm phạm vi Nội quy lao động, biết phần nào cần HR xác nhận và không nhầm dữ liệu dự án với chính sách HR.",
        "activity": "Đề xuất: lập checklist ngày đầu từ nguồn nội bộ và đánh dấu từng điểm cần HR xác nhận bản gốc.",
        "first_activity": "Đề xuất: chọn một quy định nội bộ, ghi citation và tách rõ điều bắt buộc với câu hỏi cần HR xác nhận.",
        "gaps": [
            "quy trình cấp tài khoản, hồ sơ, phúc lợi và payroll",
            "đầu mối HR/Operations và SLA xử lý yêu cầu nhân sự",
            "quy trình đào tạo bắt buộc, bảo mật và lưu hồ sơ",
        ],
        "questions": [
            "Quy trình hồ sơ, tài khoản, phúc lợi/payroll và đầu mối HR? — `[Chưa có trong KB]`",
            "Đào tạo bắt buộc và quy trình lưu hồ sơ nhân sự? — `[Chưa có trong KB]`",
        ],
    },
    "general": {
        "label": "General onboarding",
        "title": "Trọng tâm vai trò và khoảng trống cần xác nhận",
        "outcome": "Biết dùng nguồn KB cho onboarding và nhận diện thông tin riêng của vai trò chưa được công bố.",
        "activity": "Đề xuất: chọn một task hoặc quy định, truy nguồn và ghi các câu hỏi cần người phụ trách xác nhận.",
        "first_activity": "Đề xuất: trả lời câu hỏi onboarding bằng citation và đánh dấu dữ liệu còn thiếu.",
        "gaps": ["quy trình và tiêu chí chuyên biệt của vai trò người học"],
        "questions": ["Quy trình chuyên biệt của vai trò người học? — `[Chưa có trong KB]`"],
    },
}

ROLE_ALIASES = {
    "dev": "developer",
    "backend": "developer",
    "frontend": "developer",
    "backend-developer": "developer",
    "frontend-developer": "developer",
    "engineering": "developer",
    "tester": "qa",
    "qa-engineer": "qa",
    "qa-tester": "qa",
    "kiem-thu": "qa",
    "quality-assurance": "qa",
    "quality": "qa",
    "pm": "project-manager",
    "project-management": "project-manager",
    "projectmanager": "project-manager",
    "quan-ly-du-an": "project-manager",
    "hr": "hr-operations",
    "operations": "hr-operations",
    "ops": "hr-operations",
    "nhan-su": "hr-operations",
    "van-hanh": "hr-operations",
}

DEFAULT_ROLES_CONFIG = Path(__file__).resolve().parents[1] / "config" / "role_profiles.yml"


@dataclass
class Page:
    path: Path
    relative: str
    meta: dict[str, str]
    title: str
    headings: list[str]
    bullets: list[str]
    paragraphs: list[str]
    raw: str

    @property
    def doc_id(self) -> str:
        return self.meta.get("doc_id", "")

    @property
    def raw_paths(self) -> list[str]:
        return [item.strip() for item in self.meta.get("raw_paths", "").split(",") if item.strip()]

    @property
    def visibility(self) -> str:
        return self.meta.get("visibility", "").lower()

    @property
    def page_type(self) -> str:
        return self.meta.get("page", "")

    @property
    def is_history(self) -> bool:
        """Whether this page is retained for audit, not for current training."""
        return self.meta.get("retired", "").lower() in {"true", "yes", "1"} or bool(
            self.meta.get("superseded_by", "").strip()
        )

    @property
    def is_ocr_source(self) -> bool:
        """Return true only when provenance explicitly identifies OCR output.

        A document name such as ``noi-quy-lao-dong.md`` is not evidence of OCR;
        the previous substring check incorrectly marked the Markdown re-ingest.
        """
        truthy = {"true", "yes", "1"}
        if self.meta.get("ocr", "").strip().lower() in truthy:
            return True
        provenance = " ".join(
            self.meta.get(key, "")
            for key in ("extractor", "kind", "generated_by", "source_type")
        ).lower()
        return "ocr" in provenance or "vision-2pass" in provenance

    @property
    def searchable(self) -> str:
        return " ".join(
            [self.title, self.meta.get("domain", ""), self.meta.get("project", ""),
             self.meta.get("source_name", ""), " ".join(self.meta.get("raw_paths", "").split(",")),
             self.relative]
        ).lower()


@dataclass
class Module:
    id: str
    title: str
    outcome: str
    pages: list[Page] = field(default_factory=list)
    activity: str = ""
    gaps: list[str] = field(default_factory=list)
    scope: str = "project_dynamic"


def load_role_profiles(config_path: Path | None = None) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Load editable role profiles, retaining safe built-in fallbacks."""
    profiles = {key: dict(value) for key, value in ROLE_PROFILES.items()}
    aliases = dict(ROLE_ALIASES)
    path = config_path or DEFAULT_ROLES_CONFIG
    if not path.is_file():
        return profiles, aliases
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return profiles, aliases
    aliases.update({str(key): str(value) for key, value in (data.get("aliases") or {}).items()})
    for key, value in (data.get("roles") or {}).items():
        if not isinstance(value, dict):
            continue
        merged = dict(profiles.get(str(key), profiles["general"]))
        merged.update(value)
        for list_key in ("gaps", "questions"):
            if not isinstance(merged.get(list_key), list):
                merged[list_key] = []
        profiles[str(key)] = merged
    return profiles, aliases


def normalise_role(role: str, aliases: dict[str, str] | None = None,
                   profiles: dict[str, dict[str, object]] | None = None) -> str:
    value = unicodedata.normalize("NFKD", role).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    aliases = aliases or ROLE_ALIASES
    profiles = profiles or ROLE_PROFILES
    return aliases.get(value, value if value in profiles else "general")


def role_profile(role: str, profiles: dict[str, dict[str, object]] | None = None,
                 aliases: dict[str, str] | None = None) -> tuple[str, dict[str, object]]:
    profiles = profiles or ROLE_PROFILES
    key = normalise_role(role, aliases, profiles)
    return key, profiles.get(key, profiles["general"])


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}, text
    meta: dict[str, str] = {}
    current_key: str | None = None
    list_values: list[str] = []
    for line in lines[1:end]:
        if re.match(r"^\s*-\s+", line) and current_key:
            list_values.append(re.sub(r"^\s*-\s+", "", line).strip().strip('"\''))
            meta[current_key] = ",".join(list_values)
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            continue
        current_key, value = match.groups()
        list_values = []
        value = value.strip().strip('"\'')
        if value.startswith("{"):
            value = value.replace("{", "").replace("}", "")
        meta[current_key] = value
    return meta, "\n".join(lines[end + 1:])


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def parse_page(path: Path, kb_root: Path) -> Page | None:
    if path.name in SKIP_NAMES or path.name.startswith("."):
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, body = parse_frontmatter(raw)
    if not meta or not meta.get("page"):
        return None
    headings = [_clean_line(line.lstrip("#").strip()) for line in body.splitlines()
                if line.startswith("#") and _clean_line(line.lstrip("#").strip())]
    bullets = [
        _clean_line(re.sub(r"^\s*[-*]\s+", "", line))
        for line in body.splitlines()
        if re.match(r"^\s*[-*]\s+", line)
    ]
    paragraphs: list[str] = []
    block: list[str] = []
    for line in body.splitlines() + [""]:
        if _clean_line(line) and not line.lstrip().startswith(("#", "-", "*", "|")):
            block.append(_clean_line(line))
        elif block:
            paragraphs.append(" ".join(block))
            block = []
    title = meta.get("name", "") or (headings[0] if headings else path.stem)
    rel = path.relative_to(kb_root).as_posix()
    return Page(path, rel, meta, title, headings, bullets, paragraphs, raw)


def discover_pages(kb_root: Path) -> list[Page]:
    pages: list[Page] = []
    wiki = kb_root / "wiki"
    for area in AREA_NAMES:
        root = wiki / area
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            page = parse_page(path, kb_root)
            if page and page.visibility in ALLOWED_VISIBILITY and not page.is_history:
                pages.append(page)
    return pages


def _has_any(text: str, words: Iterable[str]) -> bool:
    return any(word.lower() in text for word in words)


def classify_pages(pages: list[Page], project: str) -> tuple[list[Page], list[Page], list[Page]]:
    project_l = project.lower()
    internal: list[Page] = []
    project_pages: list[Page] = []
    team: list[Page] = []
    for page in pages:
        if page.page_type == "entity-person":
            if _has_any(page.searchable, [project_l]):
                team.append(page)
            continue
        policy = _has_any(page.searchable, ["noi-quy", "policy", "handbook", "hr", "mor-software"])
        belongs_project = page.meta.get("project", "").lower() == project_l or _has_any(
            page.searchable, [project_l, f"{project_l}-"])
        if policy:
            internal.append(page)
        elif belongs_project:
            project_pages.append(page)
        elif page.visibility == "internal":
            # Keep future company documents even when their filename does not
            # use the current policy/HR vocabulary, but never mix project pages
            # into the company-policy module.
            internal.append(page)
    return internal, project_pages, team


def load_document_registry(kb_root: Path) -> dict[str, dict[str, str]]:
    """Map published raw paths to reader-facing source provenance."""
    path = kb_root / "documents.yml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    registry: dict[str, dict[str, str]] = {}
    for document in data.get("documents", []) or []:
        doc_id = str(document.get("doc_id", "")).strip()
        version = str(document.get("version", "unknown")).strip()
        if not doc_id:
            continue
        for raw_path in document.get("raw_paths", []) or []:
            registry[Path(str(raw_path)).as_posix()] = {
                "doc_id": doc_id,
                "version": version,
                "source_name": str(document.get("source_name") or ""),
                "source_origin": str(document.get("source_origin") or ""),
                "updated_at": str(document.get("updated_at") or ""),
                "updated_by": str(document.get("updated_by") or ""),
                "original": Path(str(document.get("original") or "")).name,
            }
    return registry


def _display_date(value: str) -> str:
    date = str(value or "").strip().split("T", 1)[0]
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date)
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}" if match else (date or "chưa ghi nhận")


def _citation(page: Page, registry: dict[str, dict[str, str]] | None = None) -> str:
    registry = registry or {}
    records = [registry.get(raw_path) for raw_path in page.raw_paths]
    records = [record for record in records if record]
    record = records[0] if records else {}
    source_name = record.get("source_name") or page.meta.get("source_name") or (
        Path(page.raw_paths[0]).name if page.raw_paths else page.relative)
    origin = record.get("source_origin", "").strip()
    source = f"`{origin or source_name}`"
    return (f"Nguồn: {source} · cập nhật ngày {_display_date(record.get('updated_at', ''))} · "
            f"bởi {record.get('updated_by') or 'chưa ghi nhận'}")


def _source_points(page: Page, limit: int = 5) -> list[str]:
    points: list[str] = []
    for item in page.bullets:
        if len(item) >= 18 and item not in points:
            points.append(item)
        if len(points) >= limit:
            break
    if len(points) < limit:
        for paragraph in page.paragraphs:
            if len(paragraph) >= 35 and paragraph not in points:
                points.append(paragraph)
            if len(points) >= limit:
                break
    return points[:limit]


def _module(id_: str, title: str, outcome: str, pages: list[Page], activity: str,
            gaps: Iterable[str] | None = None, scope: str | None = None) -> Module:
    default_scopes = {
        "company-basics": "policy_fixed",
        "workplace-practice": "policy_fixed",
        "project-context": "project_dynamic",
        "team-workflow": "project_dynamic",
        "role-readiness": "role_guidance",
        "first-delivery": "project_dynamic",
    }
    return Module(id_, title, outcome, pages, activity, list(gaps or []),
                  scope or default_scopes.get(id_, "project_dynamic"))


def build_modules(internal: list[Page], project_pages: list[Page], team: list[Page],
                  role: str = "developer", profiles: dict[str, dict[str, object]] | None = None,
                  aliases: dict[str, str] | None = None) -> list[Module]:
    role_key, profile = role_profile(role, profiles, aliases)
    policy_overview = [p for p in internal if "--chuong-" not in p.relative.lower()]
    workplace = [
        p for p in internal
        if re.search(r"\bCH(?:Ư|Æ¯)ƠNG\s*[3-9]\b", p.title, re.IGNORECASE)
        or re.search(r"\bchuong-[3-9]\b", p.relative, re.IGNORECASE)
    ]
    role_pages = {
        "hr-operations": policy_overview,
        "project-manager": project_pages,
    }.get(role_key, project_pages + team)
    role_pages = list({page.path: page for page in role_pages}.values())
    return [
        _module("company-basics", "Nội bộ công ty và phạm vi áp dụng",
                "Biết tài liệu nào là quy định bắt buộc và khi nào cần hỏi HR.", policy_overview,
                "Đánh dấu ba quy định người học cần xác nhận với HR trong ngày đầu."),
        _module("workplace-practice", "Thời gian, tác phong và an toàn",
                "Biết các điểm cần tuân thủ tại nơi làm việc và các giới hạn của nguồn hiện có.",
                workplace,
                "Viết lại một checklist trước khi bắt đầu ngày làm việc; không tự thêm giờ/điều kiện ngoài nguồn."),
        _module("project-context", "Bối cảnh và mục tiêu dự án",
                "Giải thích dự án đang quản lý những loại dữ liệu và hoạt động nào.", project_pages,
                "Mở trang nguồn dự án và chỉ ra nơi tra cứu resource, schedule, sprint, risk và issue."),
        _module("team-workflow", "Team và cách nhận task",
                "Biết thành viên/role nào đã được khai báo và cách kiểm chứng trước khi giao việc.", team,
                "Chọn một task trong dữ liệu dự án và chuẩn bị câu hỏi làm rõ owner, status, nguồn và quyền thao tác."),
        _module("role-readiness", str(profile["title"]), str(profile["outcome"]), role_pages,
                str(profile["activity"]), profile["gaps"]),
        _module("first-delivery", "Thực hành tuần đầu",
                "Hoàn thành một phiên hỏi đáp có citation và biết cách báo thiếu dữ liệu.", project_pages + team,
                str(profile["first_activity"])),
    ]


def render_pages(pages: list[Page], registry: dict[str, dict[str, str]] | None = None) -> str:
    if not pages:
        return "- `[Chưa có trong KB]` Không tìm thấy nguồn phù hợp."
    chunks: list[str] = []
    for page in pages:
        chunks.append(f"- **{page.title}** — {_citation(page, registry)}")
        points = _source_points(page)
        if points:
            chunks.extend(f"  - {point}" for point in points)
        else:
            chunks.append("  - `[Chưa có trong KB]` Trang không có đoạn tóm tắt đọc được.")
        if page.is_ocr_source:
            chunks.append("  - Lưu ý: nguồn có thể là OCR; đối chiếu bản gốc trước khi dùng làm quy định pháp lý.")
    return "\n".join(chunks)


def reuse_fixed_policy_modules(previous_text: str, generated_text: str) -> str:
    """Keep policy-fixed module blocks byte-for-byte during project refresh."""
    block_re = re.compile(r"(?ms)^### 2\.\d+ .*?(?=^### 2\.\d+ |^## 3\.|\Z)")

    def blocks(text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for match in block_re.finditer(text):
            block = match.group(0)
            heading = block.splitlines()[0]
            title = heading.split(" ", 2)[-1]
            if "- **Scope:** `policy_fixed`" in block:
                result[title] = block
        return result

    fixed = blocks(previous_text)
    for title, old_block in fixed.items():
        pattern = re.compile(r"(?ms)^### 2\.\d+ " + re.escape(title) + r".*?(?=^### 2\.\d+ |^## 3\.|\Z)")
        generated_text, replaced = pattern.subn(old_block, generated_text, count=1)
        if replaced != 1:
            raise ValueError(f"không tìm thấy policy module để reuse: {title}")
    return generated_text


def check_freshness(kb_root: Path) -> dict[str, str]:
    """Read knowledge-base freshness without making it a hard dependency."""
    script_dir = kb_root / "scripts"
    if not (script_dir / "versioning.py").is_file():
        return {"state": "unknown", "reason": "Không tìm thấy scripts/versioning.py"}
    try:
        script_text = str(script_dir)
        if script_text not in sys.path:
            sys.path.insert(0, script_text)
        import versioning  # type: ignore

        result = versioning.check(kb_root)
        index_state = (result.get("indexes") or {}).get("state")
        state = result.get("state", "unknown")
        if state == "fresh" and index_state and index_state != "fresh":
            state = "stale"
        reason = result.get("reason", "")
        if index_state and index_state != "fresh":
            errors = "; ".join((result.get("indexes") or {}).get("errors") or [])
            reason = f"{reason}; {errors}" if errors else reason
        return {"state": state, "reason": reason, "version": str(result.get("version", ""))}
    except Exception as exc:  # pragma: no cover - defensive boundary for optional metadata
        return {"state": "unknown", "reason": f"Không đọc được freshness: {type(exc).__name__}"}


def render_handbook(project: str, role: str, name: str, pages: list[Page], internal: list[Page], project_pages: list[Page], team: list[Page], freshness: dict[str, str] | None = None, registry: dict[str, dict[str, str]] | None = None, profiles: dict[str, dict[str, object]] | None = None, aliases: dict[str, str] | None = None, artifact_scope: str = "all") -> str:
    today = dt.date.today().isoformat()
    role_key, profile = role_profile(role, profiles, aliases)
    modules = build_modules(internal, project_pages, team, role_key, profiles, aliases)
    freshness = freshness or {"state": "unknown", "reason": "Chưa kiểm tra metadata freshness"}
    freshness_state = freshness.get("state", "unknown")
    freshness_note = freshness.get("reason", "")
    lines = [
        f"# Handbook onboarding — {name}",
        "",
        f"- **Dự án:** `{project}`",
        f"- **Vai trò:** `{role}`",
        f"- **Hồ sơ đào tạo:** `{profile['label']}`",
        f"- **Snapshot KB:** `{today}`",
        f"- **Freshness KB:** `{freshness_state}`" + (f" — {freshness_note}" if freshness_note else ""),
        f"- **Regeneration scope:** `{artifact_scope}`",
        "- **Policy scope:** `policy_fixed` — Nội quy/chính sách cố định, không refresh theo project.",
        "- **Project scope:** `project_dynamic` — resource, sprint, team, risk và workflow có thể refresh khi project thay đổi.",
        "- **Mục đích:** tài liệu học tập tổng hợp từ wiki đã xuất bản; không thay thế tài liệu gốc hoặc phê duyệt của HR/PM.",
        "",
        "## 1. Mục tiêu sau khi hoàn thành",
        "",
        "- Phân biệt quy định nội bộ, hướng dẫn dự án và đề xuất thực hành.",
        "- Biết tìm nguồn, đọc `doc_id/version/visibility` và trích citation khi trả lời.",
        "- Biết báo `Chưa có trong KB` thay vì suy đoán.",
        "- Biết các điểm cần xác nhận với HR/PM trước khi thực hiện hành động có tác động.",
        "",
        "## 2. Lộ trình training",
        "",
    ]
    for number, module in enumerate(modules, 1):
        coverage = "partial" if module.pages and module.gaps else ("covered" if module.pages else "not_in_kb")
        lines.extend([
            f"### 2.{number} {module.title}",
            "",
            f"- **Kết quả cần đạt:** {module.outcome}",
            f"- **Scope:** `{module.scope}`",
            f"- **Coverage:** `{coverage}`",
            f"- **Hoạt động gợi ý:** {module.activity}",
            "",
            "**Nội dung có nguồn:**",
            render_pages(module.pages, registry),
            "",
        ])
        if module.gaps:
            lines.extend(["**Khoảng trống cần xác nhận:**", ""])
            lines.extend(f"- `[Chưa có trong KB]` {gap}" for gap in module.gaps)
            lines.append("")
    lines.extend([
        "## 3. Checklist onboarding",
        "",
        "### Trước ngày đầu",
        "",
        "- [ ] Xác nhận vai trò, project và người hướng dẫn với PM/HR.",
        "- [ ] Đọc các nguồn nội bộ trong ma trận nguồn; ghi lại điểm cần hỏi lại.",
        "- [ ] Không coi thông tin thiếu trong KB là khẳng định không tồn tại.",
        "",
        "### Tuần đầu",
        "",
        "- [ ] Tra được trang overview của project và các entity team liên quan.",
        "- [ ] Trả lời được câu hỏi onboarding kèm citation.",
        "- [ ] Thử một quy trình read-only; chưa tự ghi Jira/Sheet/Slack.",
        "",
        "### Trước task đầu tiên",
        "",
        "- [ ] Xác nhận acceptance criteria, owner, status và nguồn dữ liệu.",
        "- [ ] Xác nhận quyền thao tác; mọi write action phải qua approval của skill tương ứng.",
        "- [ ] Biết nơi báo blocker, risk hoặc thông tin mâu thuẫn.",
        "",
        "## 4. Câu hỏi kiểm tra",
        "",
        "1. Nguồn nào là quy định nội bộ và phải đối chiếu bản gốc trước khi áp dụng?",
        "2. Project overview nằm ở đâu và nó dẫn tới những loại dữ liệu nào?",
        "3. Khi không tìm thấy thông tin về tech-stack/owner, cần trả lời thế nào? — **`Chưa có trong KB`**, không suy diễn.",
        "4. Citation tối thiểu cần có những trường nào? — tên file nguồn, ngày cập nhật và người cập nhật.",
        "5. Ai có quyền phê duyệt thay đổi dữ liệu dự án? — `[Chưa có trong KB]` nếu nguồn hiện tại chưa khai báo.",
        *[f"{6 + index}. {question}" for index, question in enumerate(profile["questions"])],
        "",
        "## 5. Ma trận nguồn",
        "",
    ])
    if pages:
        for page in pages:
            lines.append(f"- **{page.title}** — {_citation(page, registry)}")
    else:
        lines.append("- `[Chưa có trong KB]` Không có trang hợp lệ trong phạm vi đã chọn.")
    lines.extend([
        "",
        "## 6. Giới hạn cần xác nhận",
        "",
        f"- Freshness hiện tại: `{freshness_state}`" + (f" — {freshness_note}" if freshness_note else ""),
        "- Nếu freshness là `stale` hoặc `unknown`, rebuild/kiểm tra `knowledge-base` trước khi dùng handbook cho quyết định mới.",
        "- Tài liệu chỉ phản ánh snapshot KB tại thời điểm sinh; kiểm tra freshness trước khi dùng cho quyết định mới.",
        "- Thông tin không xuất hiện trong ma trận nguồn không được coi là không tồn tại.",
        "- HR/PM phải xác nhận nội dung thiếu hoặc mâu thuẫn trước khi phát hành handbook chính thức.",
        "",
    ])
    if any(page.is_ocr_source for page in pages):
        lines.insert(-2, "- Có nguồn OCR trong snapshot này; đối chiếu bản gốc và hỏi HR khi có nghi ngờ.")
    return "\n".join(lines)


def default_kb_root() -> Path:
    here = Path(__file__).resolve()
    import os
    configured = os.environ.get("KNOWLEDGE_BASE_ROOT")
    return Path(configured or here.parents[2] / "knowledge-base")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-root", type=Path, default=default_kb_root())
    parser.add_argument("--project", default="nexus")
    parser.add_argument("--role", default="developer")
    parser.add_argument("--name", default="Nhân viên mới")
    parser.add_argument("--roles-config", type=Path, default=None,
                        help="YAML config role profiles; mặc định config/role_profiles.yml")
    parser.add_argument("--scope", choices=("all", "project_dynamic"), default="all",
                        help="all hoặc chỉ refresh module project/team từ artifact trước")
    parser.add_argument("--previous", type=Path, default=None,
                        help="handbook hiện tại; bắt buộc khi --scope project_dynamic")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    kb_root = args.kb_root.resolve()
    if not (kb_root / "wiki").is_dir():
        print(f"ERROR: KB root không hợp lệ: {kb_root}", file=sys.stderr)
        return 2
    if args.scope == "project_dynamic" and not args.previous:
        print("ERROR: --scope project_dynamic cần --previous để giữ nguyên policy_fixed", file=sys.stderr)
        return 2
    pages = discover_pages(kb_root)
    internal, project_pages, team = classify_pages(pages, args.project)
    selected = sorted({p.path: p for p in internal + project_pages + team}.values(), key=lambda p: p.relative)
    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    freshness = check_freshness(kb_root)
    registry = load_document_registry(kb_root)
    roles_config = args.roles_config
    if roles_config and not roles_config.is_absolute():
        roles_config = Path.cwd() / roles_config
    profiles, aliases = load_role_profiles(roles_config)
    rendered = render_handbook(args.project, args.role, args.name, selected, internal, project_pages, team,
                               freshness, registry, profiles, aliases, args.scope)
    if args.scope == "project_dynamic":
        previous = args.previous
        if not previous.is_absolute():
            previous = Path.cwd() / previous
        try:
            rendered = reuse_fixed_policy_modules(previous.read_text(encoding="utf-8"), rendered)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"ERROR: không đọc được --previous: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"ERROR: không reuse được policy_fixed: {exc}", file=sys.stderr)
            return 2
    output.write_text(rendered, encoding="utf-8")
    print(f"created {output} ({len(selected)} sources; internal={len(internal)}, project={len(project_pages)}, team={len(team)}; freshness={freshness.get('state', 'unknown')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
