#!/usr/bin/env python3
"""GATE 1 — NGUỒN NGUYÊN VẸN.

`originals/` là tầng bất biến: mất là mất thật, và KHÔNG được sửa. Cổng này canh
điều đó bằng MÁY, không bằng niềm tin:

  - Lần đầu (hoặc --reinit): ghi sha256 mọi file trong originals/ -> originals/MANIFEST.sha256
  - Lần sau: đối chiếu. File THIẾU hoặc sha256 LỆCH -> HALT.
    Một original bị sửa nghĩa là MỌI tầng dẫn xuất từ nó (raw/ wiki/ derived/) đã
    dựng trên nền sai — và không cổng nào khác bắt được, vì chúng tin originals/.

  File MỚI thêm vào originals/ chỉ CẢNH BÁO (tầng này append-only: "chỉ thêm,
  không sửa, không xoá") — chạy --reinit để đưa nó vào manifest một cách CÓ CHỦ Ý.

Đặt ở ĐẦU pipeline, trước Stage 2 — đúng vị trí Gate 1 trong sơ đồ IngestFlow.

  python3 scripts/gate1_integrity.py            # verify (tự khởi tạo nếu chưa có manifest)
  python3 scripts/gate1_integrity.py --reinit   # ghi lại manifest khi CỐ Ý đổi originals/
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "originals"
MANIFEST = ORIG / "MANIFEST.sha256"
R, G, Y, D, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


class Halt(Exception):
    """Gate chặn: dừng pipeline, báo người."""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan():
    """sha256 mọi file trong originals/ (trừ chính manifest và .gitkeep)."""
    files = {}
    for p in sorted(ORIG.rglob("*")):
        if not p.is_file() or p == MANIFEST or p.name == ".gitkeep":
            continue
        files[p.relative_to(ORIG).as_posix()] = sha256(p)
    return files


def read_manifest():
    rec = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, rel = line.partition("  ")
        rec[rel] = digest
    return rec


def write_manifest(files):
    lines = [
        "# GATE 1 — sha256 của originals/ (tầng bất biến). KHÔNG sửa tay.",
        "# Sinh bởi scripts/gate1_integrity.py. Đổi original -> chạy --reinit CÓ CHỦ Ý.",
        "",
    ]
    lines += [f"{d}  {rel}" for rel, d in sorted(files.items())]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv):
    if not ORIG.exists():
        raise Halt("không có thư mục originals/")
    files = scan()
    if not files:
        raise Halt("originals/ rỗng — không có gì để canh")

    if "--reinit" in argv or not MANIFEST.exists():
        action = "GHI LẠI" if MANIFEST.exists() else "KHỞI TẠO"
        write_manifest(files)
        print(f"{G}GATE 1 · {action} manifest{OFF} — {len(files)} file")
        for rel in files:
            print(f"  · {rel}")
        return 0

    want = read_manifest()
    errs = []
    for rel, d in want.items():
        if rel not in files:
            errs.append(f"THIẾU FILE: {rel} (có trong manifest, không còn trong originals/)")
        elif files[rel] != d:
            errs.append(f"SHA256 LỆCH: {rel} — original đã bị SỬA kể từ lần ghi manifest")
    new = [rel for rel in files if rel not in want]

    print(f"GATE 1 · {len(want)} file trong manifest")
    for rel in new:
        print(f"{Y}⚠ file mới chưa vào manifest: {rel} — chạy --reinit nếu cố ý thêm{OFF}")
    if errs:
        for e in errs:
            print(f"{R}✗ {e}{OFF}")
        raise Halt(f"{len(errs)} vi phạm toàn vẹn nguồn — originals/ đã đổi. "
                   f"Không dựng tiếp trên nền sai.")
    print(f"{G}GATE 1 XANH{OFF} — mọi original khớp sha256 ({len(want)} file"
          f"{f', {len(new)} file mới cảnh báo' if new else ''})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Halt as e:
        print(f"\n{R}✗ HALT — {e}{OFF}", file=sys.stderr)
        sys.exit(1)
