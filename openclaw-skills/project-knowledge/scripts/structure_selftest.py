#!/usr/bin/env python3
"""Offline Stage 3 numeric-preservation tests."""
import numeric_guard


def main() -> int:
    good = "Kế hoạch cần 45.5 giờ, bắt đầu 2026-07-27."
    assert numeric_guard.check_transform(good, "Bắt đầu 2026-07-27; cần 45.5 giờ.") == ([], [])
    errors, _ = numeric_guard.check_transform(good, "Bắt đầu 2026-07-27; cần 46 giờ.")
    assert errors and any("46" in error for error in errors)
    errors, _ = numeric_guard.check_transform(good, "Bắt đầu 2026-07-28; cần 45.5 giờ.")
    assert errors and any("2026-07-28" in error for error in errors)
    errors, _ = numeric_guard.check_transform(good, "Bắt đầu 2026-07-27.")
    assert errors and any("45.5" in error for error in errors)
    print("✓ structure numeric gate self-test: 4/4 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
