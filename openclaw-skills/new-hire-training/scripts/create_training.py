#!/usr/bin/env python3
"""Build a provenance-first new-hire training handbook from project-knowledge wiki pages."""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ALLOWED_VISIBILITY = {"public", "internal"}
SKIP_NAMES = {"index.md", "log.md", ".gitkeep"}
AREA_NAMES = ("sources", "entities", "concepts", "case-studies")


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
    def visibility(self) -> str:
        return self.meta.get("visibility", "").lower()

    @property
    def page_type(self) -> str:
        return self.meta.get("page", "")

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
        if re.match(r"^\s+-\s+", line) and current_key:
            list_values.append(re.sub(r"^\s+-\s+", "", line).strip().strip('"\''))
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
            if page and page.visibility in ALLOWED_VISIBILITY:
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


def _citation(page: Page) -> str:
    version = page.meta.get("version", "unknown")
    doc_id = page.doc_id or "unknown"
    return f"`{page.relative}` · `doc_id={doc_id}` · `version={version}` · `visibility={page.visibility}`"


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


def _module(id_: str, title: str, outcome: str, pages: list[Page], activity: str) -> Module:
    return Module(id_, title, outcome, pages, activity)


def build_modules(internal: list[Page], project_pages: list[Page], team: list[Page]) -> list[Module]:
    policy_overview = [p for p in internal if "--chuong-" not in p.relative.lower()]
    workplace = [
        p for p in internal
        if re.search(r"\bCH(?:Ư|Æ¯)ƠNG\s*[3-9]\b", p.title, re.IGNORECASE)
        or re.search(r"\bchuong-[3-9]\b", p.relative, re.IGNORECASE)
    ]
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
        _module("first-delivery", "Thực hành tuần đầu",
                "Hoàn thành một phiên hỏi đáp có citation và biết cách báo thiếu dữ liệu.", project_pages + team,
                "Trả lời ba câu hỏi onboarding bằng KB; câu nào không có dữ liệu phải ghi `Chưa có trong KB`."),
    ]


def render_pages(pages: list[Page]) -> str:
    if not pages:
        return "- `[Chưa có trong KB]` Không tìm thấy nguồn phù hợp."
    chunks: list[str] = []
    for page in pages:
        chunks.append(f"- **{page.title}** — {_citation(page)}")
        points = _source_points(page)
        if points:
            chunks.extend(f"  - {point}" for point in points)
        else:
            chunks.append("  - `[Chưa có trong KB]` Trang không có đoạn tóm tắt đọc được.")
        if _has_any(page.searchable, ["ocr", "noi-quy"]):
            chunks.append("  - Lưu ý: nguồn có thể là OCR; đối chiếu bản gốc trước khi dùng làm quy định pháp lý.")
    return "\n".join(chunks)


def check_freshness(kb_root: Path) -> dict[str, str]:
    """Read project-knowledge freshness without making it a hard dependency."""
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


def render_handbook(project: str, role: str, name: str, pages: list[Page], internal: list[Page], project_pages: list[Page], team: list[Page], freshness: dict[str, str] | None = None) -> str:
    today = dt.date.today().isoformat()
    modules = build_modules(internal, project_pages, team)
    freshness = freshness or {"state": "unknown", "reason": "Chưa kiểm tra metadata freshness"}
    freshness_state = freshness.get("state", "unknown")
    freshness_note = freshness.get("reason", "")
    lines = [
        f"# Handbook onboarding — {name}",
        "",
        f"- **Dự án:** `{project}`",
        f"- **Vai trò:** `{role}`",
        f"- **Snapshot KB:** `{today}`",
        f"- **Freshness KB:** `{freshness_state}`" + (f" — {freshness_note}" if freshness_note else ""),
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
        coverage = "covered" if module.pages else "not_in_kb"
        lines.extend([
            f"### 2.{number} {module.title}",
            "",
            f"- **Kết quả cần đạt:** {module.outcome}",
            f"- **Coverage:** `{coverage}`",
            f"- **Hoạt động gợi ý:** {module.activity}",
            "",
            "**Nội dung có nguồn:**",
            render_pages(module.pages),
            "",
        ])
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
        "4. Citation tối thiểu cần có những trường nào? — đường dẫn wiki, `doc_id`, `version`, `visibility`.",
        "5. Ai có quyền phê duyệt thay đổi dữ liệu dự án? — `[Chưa có trong KB]` nếu nguồn hiện tại chưa khai báo.",
        "",
        "## 5. Ma trận nguồn",
        "",
    ])
    if pages:
        for page in pages:
            lines.append(f"- **{page.title}** — {_citation(page)}")
    else:
        lines.append("- `[Chưa có trong KB]` Không có trang hợp lệ trong phạm vi đã chọn.")
    lines.extend([
        "",
        "## 6. Giới hạn cần xác nhận",
        "",
        f"- Freshness hiện tại: `{freshness_state}`" + (f" — {freshness_note}" if freshness_note else ""),
        "- Nếu freshness là `stale` hoặc `unknown`, rebuild/kiểm tra `project-knowledge` trước khi dùng handbook cho quyết định mới.",
        "- Tài liệu chỉ phản ánh snapshot KB tại thời điểm sinh; kiểm tra freshness trước khi dùng cho quyết định mới.",
        "- Các trang OCR có thể có sai số nhận dạng; đối chiếu bản gốc và hỏi HR khi có nghi ngờ.",
        "- Thông tin không xuất hiện trong ma trận nguồn không được coi là không tồn tại.",
        "- HR/PM phải xác nhận nội dung thiếu hoặc mâu thuẫn trước khi phát hành handbook chính thức.",
        "",
    ])
    return "\n".join(lines)


def default_kb_root() -> Path:
    here = Path(__file__).resolve()
    return Path(__import__("os").environ.get("PROJECT_KNOWLEDGE_ROOT", here.parents[2] / "project-knowledge"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-root", type=Path, default=default_kb_root())
    parser.add_argument("--project", default="nexus")
    parser.add_argument("--role", default="developer")
    parser.add_argument("--name", default="Nhân viên mới")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    kb_root = args.kb_root.resolve()
    if not (kb_root / "wiki").is_dir():
        print(f"ERROR: KB root không hợp lệ: {kb_root}", file=sys.stderr)
        return 2
    pages = discover_pages(kb_root)
    internal, project_pages, team = classify_pages(pages, args.project)
    selected = sorted({p.path: p for p in internal + project_pages + team}.values(), key=lambda p: p.relative)
    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    freshness = check_freshness(kb_root)
    output.write_text(render_handbook(args.project, args.role, args.name, selected, internal, project_pages, team, freshness), encoding="utf-8")
    print(f"created {output} ({len(selected)} sources; internal={len(internal)}, project={len(project_pages)}, team={len(team)}; freshness={freshness.get('state', 'unknown')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
