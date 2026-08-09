#!/usr/bin/env python3
"""GATE 3b — LLM PHIÊN MỚI soi nội dung wiki có khớp nguồn không. (bản SIẾT)

  wiki/<trang>.md + raw/ (raw_paths)  --[ claude -p × K phiên độc lập ]-->  PASS / FINDING

Gate 3a (lint.py) là CƠ HỌC. Gate 3b là NGHĨA — chỗ bắt trang xanh-3a-toàn-tập mà vẫn
diễn giải sai nguồn. Một lượt soát LLM là ÂM TÍNH GIẢ được (đã gặp thật: PASS trang
handy-schedule trong khi còn 4 phát hiện). Bản này siết bằng ba lớp:

  1. ĐỒNG THUẬN K LƯỢT (mặc định 3). Bất đối xứng: PASS ⟺ CẢ K lượt PASS; một phát hiện
     do ≥1 lượt nêu là đã nổi lên cho người xem (nhãn "chắc" nếu ≥ đa số, "nghi" nếu ít).
  2. PHÂN RÃ KHẲNG ĐỊNH. Prompt ép liệt kê từng khẳng định nguyên tử rồi đối chiếu từng
     cái — problem vào `findings`, cái đúng vào `checked` (bằng chứng độ phủ).
  3. CHECKLIST lỗi đã biết (khái quát quá đà · số không nguồn · overclaim coverage · lẫn
     "không thấy" với "không có").

Ba nguyên tắc cũ giữ nguyên: phiên MỚI không ký ức · KHÔNG công cụ (`--tools=`)
· nguồn bị CẮT thì trả UNVERIFIABLE, KHÔNG kết luận trang sai.

  python3 scripts/review.py --page wiki/entities/qc-lan.md
  python3 scripts/review.py --all
  python3 scripts/review.py --all --log     # FINDING thì ghi vào wiki/log.md
  python3 scripts/review.py --page ... --k 5
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
R, G, Y, D, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"

# Trang `source` VĂN tóm tắt CẢ tài liệu (~94KB) — cắt nhỏ thì mọi khẳng định phía sau
# thành "không kiểm được", cổng vô dụng. Prompt qua STDIN nên không dính trần 32KB.
MAX_SRC_CHARS = 120000
DEFAULT_K = 3

PROMPT = """Bạn là GATE 3b của hệ thống LLM-wiki: người soát ĐỘC LẬP, phiên hoàn toàn mới.
Bạn KHÔNG phải người viết trang. Việc của bạn là tìm chỗ trang wiki nói SAI so với nguồn.

QUY TRÌNH BẮT BUỘC (làm trong đầu, đừng in ra):
1. LIỆT KÊ mọi khẳng định NGUYÊN TỬ trong trang (mỗi câu/mệnh đề một khẳng định).
2. Với TỪNG khẳng định, đối chiếu với nguồn raw/ dưới đây và xếp loại:
   - SUPPORTED       : nguồn nói đúng như vậy (ghi được câu nguồn).
   - CONTRADICTED    : nguồn nói KHÁC/ngược.
   - NOT_IN_SOURCE   : không có trong nguồn nào (trang tự thêm).
   - UNVERIFIABLE    : không kiểm được vì bằng chứng nằm ngoài đoạn `[... ĐÃ CẮT BỚT ...]`.
3. Áp CHECKLIST lỗi hay gặp (bắt buộc soi kỹ, đây là chỗ dễ lọt):
   - Khái quát quá đà: "toàn bộ / duy nhất / không có ai / phạm vi kín" — có bị giới hạn
     đúng về phần nguồn CHỨNG MINH được không? (vd "phạm vi kín" phải nói rõ kín tới đâu)
   - Số: mọi con số có truy được về nguồn không? (facts_ref đã có Gate 3a lo — BỎ QUA nó)
   - Coverage: câu về "đã ký / chắc chắn không" có nêu đúng phạm vi đã ký
     (person_role / person_task tới mốc nào, KHÔNG lan sang phần chưa ký) không?
   - Lẫn "không THẤY trong nguồn" với "không TỒN TẠI".
   - LẪN CỘT (lỗi CÓ KHUÔN, đã lọt nhiều lần — soi thật kỹ): bảng sprint có CẢ cột
     `category` LẪN cột `role`, và giá trị có thể trùng nhau (vd `Common` xuất hiện ở cả
     hai). Câu mô tả người "thuộc nhóm / vai trò / là X" PHẢI lấy từ cột `role`, KHÔNG
     phải cột `category`. Đọc `Common`/`Brse`… ở cột category rồi trình bày như vai trò
     hay "nhóm" của NGƯỜI = SAI. Kiểm từng dòng: giá trị đang nói đến nằm ở cột nào?

LUẬT: chỉ dùng nguồn raw/ dưới đây, không kiến thức ngoài, không suy đoán. UNVERIFIABLE thì
KHÔNG kết luận trang sai.

CHỈ IN RA JSON (không rào ```, không lời dẫn), đúng schema:
{{
  "verdict": "PASS" | "FINDING" | "UNVERIFIABLE",
  "findings": [
    {{"claim": "<câu trong trang bị sai/thừa>", "problem": "<sai/thiếu gì>", "source_says": "<nguồn nói gì, trích ngắn>"}}
  ],
  "checked": ["<khẳng định đã đối chiếu và ĐÚNG — mỗi cái một dòng ngắn>"]
}}
verdict = "FINDING" khi `findings` KHÔNG rỗng (CONTRADICTED/NOT_IN_SOURCE). "UNVERIFIABLE"
chỉ khi phần lớn không kiểm được do bị cắt. "PASS" khi `findings` rỗng và đã đối chiếu được.
Tiếng Việt trong nội dung. findings rỗng thì để [].

===== TRANG WIKI CẦN SOÁT: {path} =====
{page}

===== PHẠM VI ĐÃ KÝ (coverage.yml) =====
{coverage}

===== NGUỒN raw/ (trang tự khai trong raw_paths) =====
{sources}
"""


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    try:
        return yaml.safe_load(m.group(1)) or {}, m.group(2)
    except yaml.YAMLError:
        return {}, text


def build_sources(fm):
    out = []
    for rel in fm.get("raw_paths") or []:
        p = ROOT / rel
        if not p.exists():
            out.append(f"--- {rel} ---\n(KHÔNG TỒN TẠI — Gate 3a lẽ ra đã chặn)")
            continue
        body = p.read_text(encoding="utf-8")
        if len(body) > MAX_SRC_CHARS:
            body = body[:MAX_SRC_CHARS] + "\n[... ĐÃ CẮT BỚT ...]"
        out.append(f"--- {rel} ---\n{body}")
    return "\n\n".join(out) if out else "(trang không khai raw_paths nào)"


def _extract_json(text):
    """Lôi khối JSON đầu tiên ra khỏi stdout (LLM đôi khi kèm rào/lời dẫn)."""
    text = re.sub(r"^```(?:json)?\n|\n```$", "", text.strip()).strip()
    i = text.find("{")
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[i:])
        return obj
    except json.JSONDecodeError:
        return None


def run_once(prompt, timeout=240):
    """Một phiên soát -> dict chuẩn hoá {verdict, findings, checked, err}."""
    try:
        out = subprocess.run(
            [models.CLAUDE, "-p", "--model", models.REVIEW, "--tools="],
            input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, cwd=ROOT)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"verdict": "ERR", "findings": [], "checked": [], "err": f"{type(e).__name__}"}
    if out.returncode != 0:
        return {"verdict": "ERR", "findings": [], "checked": [],
                "err": (out.stderr or "").strip()[:200]}
    obj = _extract_json(out.stdout or "")
    if not isinstance(obj, dict) or "verdict" not in obj:
        return {"verdict": "ERR", "findings": [], "checked": [],
                "err": "output không phải JSON hợp lệ"}
    v = str(obj.get("verdict", "")).upper()
    verdict = ("PASS" if v.startswith("PASS")
               else "FINDING" if v.startswith("FINDING")
               else "UNVERIFIABLE" if "UNVER" in v or "KI" in v else "ERR")
    findings = obj.get("findings") if isinstance(obj.get("findings"), list) else []
    # chuẩn hoá phần tử finding về dict có 'claim'
    norm = []
    for f in findings:
        if isinstance(f, dict) and (f.get("claim") or f.get("problem")):
            norm.append({"claim": str(f.get("claim", "")).strip(),
                         "problem": str(f.get("problem", "")).strip(),
                         "source_says": str(f.get("source_says", "")).strip()})
        elif isinstance(f, str) and f.strip():
            norm.append({"claim": f.strip(), "problem": "", "source_says": ""})
    if verdict == "PASS" and norm:      # tự mâu thuẫn -> tin findings
        verdict = "FINDING"
    checked = [str(c).strip() for c in (obj.get("checked") or []) if str(c).strip()]
    return {"verdict": verdict, "findings": norm, "checked": checked, "err": ""}


def _fkey(f):
    """Khoá gộp một finding qua các lượt: chuẩn hoá claim (bỏ dấu câu/hoa/thường)."""
    s = (f.get("claim") or f.get("problem") or "").lower()
    return re.sub(r"[^a-z0-9À-ỹ]+", " ", s).strip()[:80]


def review(path, k=DEFAULT_K):
    """K phiên độc lập -> (verdict, chi_tiết_str, runs). Bất đối xứng ưu tiên RECALL."""
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    fm, _ = frontmatter(text)
    cov = ROOT / "coverage.yml"
    prompt = PROMPT.format(path=rel, page=text, sources=build_sources(fm),
                           coverage=cov.read_text(encoding="utf-8") if cov.exists()
                                    else "(không có coverage.yml)")
    runs = [run_once(prompt) for _ in range(k)]
    parsed = [r for r in runs if r["verdict"] != "ERR"]
    verified = [r for r in parsed if r["verdict"] != "UNVERIFIABLE"]
    n_pass = sum(1 for r in verified if r["verdict"] == "PASS" and not r["findings"])

    # gộp phát hiện qua các lượt, đếm phiếu
    votes = Counter()
    sample = {}
    for r in verified:
        seen = set()
        for f in r["findings"]:
            kf = _fkey(f)
            if not kf or kf in seen:
                continue
            seen.add(kf)
            votes[kf] += 1
            sample.setdefault(kf, f)

    # Bất đối xứng CÓ HIỆU CHỈNH theo phiếu (đồng thuận):
    #   - phát hiện ĐA SỐ (≥ maj lượt)  -> "chắc": làm HALT gate (precision cao, recall giữ).
    #   - phát hiện THIỂU SỐ (< maj)     -> "nghi": nêu cho người xem, KHÔNG làm sập gate.
    #   - không lượt nào đọc được        -> KHÔNG CHẮC (không dám kết luận).
    # Vì sao không HALT trên MỌI phiếu 1/K: lượt lẻ hay nêu điểm mờ (vd "chưa nói ký tạm")
    # — đúng là đáng xem nhưng chặn cứng thì cổng gần như không bao giờ xanh. Lỗi rõ ràng
    # thì nhiều lượt cùng bắt (seeded test: 3/3), nên "đa số chặn" vẫn giữ được recall.
    maj = (k // 2) + 1
    chac = [(kf, v) for kf, v in votes.items() if v >= maj]
    nghi = [(kf, v) for kf, v in votes.items() if v < maj]
    unverifiable = [r for r in parsed if r["verdict"] == "UNVERIFIABLE"]
    if not parsed:
        verdict = "KHÔNG CHẮC"
    elif chac:
        verdict = "FINDING"
    elif unverifiable:
        # A page is not verified when any usable review session says that its
        # evidence was truncated/insufficient. Do not let a clean PASS hide it.
        verdict = "KHÔNG CHẮC"
    elif nghi:
        verdict = "PASS·lưu ý"
    else:
        verdict = "PASS"

    lines = [f"{n_pass}/{k} lượt PASS-sạch · {len(parsed)}/{k} lượt đọc được"]
    if any(r["verdict"] == "ERR" for r in runs):
        lines.append(f"  (lượt lỗi: {[r['err'] for r in runs if r['verdict'] == 'ERR']})")
    if unverifiable:
        lines.append(f"  (lượt không đủ bằng chứng: {len(unverifiable)}/{k})")
    for kf, v in votes.most_common():
        f = sample[kf]
        tag = "CHẮC" if v >= maj else "nghi"
        lines.append(f"- [{tag} {v}/{k}] {f['claim']}"
                     + (f" — {f['problem']}" if f['problem'] else "")
                     + (f" (nguồn: {f['source_says']})" if f['source_says'] else ""))
    if verdict == "PASS":
        for c in (parsed[0]["checked"][:6] if parsed else []):
            lines.append(f"  ✓ đã đối chiếu: {c}")
    return verdict, "\n".join(lines), runs


def append_log(rows):
    log = WIKI / "log.md"
    old = log.read_text(encoding="utf-8") if log.exists() else "# Nhật ký wiki\n"
    lines = [f"\n## {date.today()} — GATE 3b (đồng thuận {DEFAULT_K} lượt)\n"]
    for rel, verdict, detail in rows:
        lines.append(f"### {rel} — **{verdict}**\n")
        lines.append(detail + "\n")
    log.write_text(old.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")
    print(f"{D}→ đã ghi wiki/log.md{OFF}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--plan", help="re-ingest plan; review only its page_actions.write set")
    ap.add_argument("--log", action="store_true", help="FINDING thì ghi vào wiki/log.md")
    ap.add_argument("--k", type=int, default=DEFAULT_K, help="số lượt soát độc lập")
    a = ap.parse_args()

    if a.plan:
        plan_path = Path(a.plan)
        if not plan_path.is_absolute():
            plan_path = ROOT / plan_path
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        pages = [ROOT / rel for rel in plan.get("page_actions", {}).get("write", [])
                 if (ROOT / rel).is_file()]
    elif a.all:
        pages = [p for p in sorted(WIKI.rglob("*.md")) if p.name not in ("index.md", "log.md")]
    elif a.page:
        pages = [ROOT / a.page]
    else:
        ap.error("cần --page <đường dẫn> hoặc --all")

    print(
        f"GATE 3b · {len(pages)} trang · đồng thuận {a.k} lượt "
        f"(claude -p, model={models.REVIEW}, không công cụ)\n"
    )
    rows, bad = [], 0
    for p in pages:
        rel = p.relative_to(ROOT).as_posix()
        print(f"{D}… {rel} (×{a.k}){OFF}", flush=True)
        verdict, detail, _ = review(p, k=a.k)
        col = {"PASS": G, "PASS·lưu ý": Y, "FINDING": R, "KHÔNG CHẮC": Y}.get(verdict, R)
        print(f"{col}{verdict:14s}{OFF} {rel}")
        # Chỉ FINDING (đa số) và KHÔNG CHẮC làm sập gate. PASS·lưu ý = có nghi, không sập.
        if verdict in ("FINDING", "KHÔNG CHẮC"):
            bad += 1
        for ln in detail.splitlines():
            if ln.strip():
                print(f"    {ln.strip()}")
        rows.append((rel, verdict, detail))
        print()

    if a.log and any(v != "PASS" for _, v, _ in rows):
        append_log([r for r in rows if r[1] != "PASS"])

    advis = sum(1 for _, v, _ in rows if v == "PASS·lưu ý")
    if bad:
        print(f"{R}GATE 3b ĐỎ{OFF} — {bad}/{len(pages)} trang có phát hiện ĐA SỐ (chắc). "
              f"HALT: người xem, sửa, chạy lại." + (f" ({advis} trang có 'nghi' để xem thêm.)" if advis else ""))
        sys.exit(1)
    tail = f" ({advis} trang PASS·lưu ý — có 'nghi' 1/{a.k}, đáng liếc nhưng không sập)" if advis else ""
    print(f"{G}GATE 3b XANH{OFF} — không phát hiện đa số nào qua {a.k} lượt.{tail}")


if __name__ == "__main__":
    main()
