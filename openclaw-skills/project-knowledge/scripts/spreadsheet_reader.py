"""Helpers for reading XLSX sheets without trusting worksheet dimensions."""
from __future__ import annotations

from itertools import zip_longest
from typing import Any, Iterator


def iter_row_pairs(formula_sheet: Any, value_sheet: Any
                   ) -> Iterator[tuple[int, tuple[Any, ...], tuple[Any, ...]]]:
    """Yield matching formula/data-only rows.

    Some valid XLSX producers omit the worksheet ``<dimension>`` element. In
    openpyxl read-only mode that makes ``max_row`` and ``max_column`` become
    ``None`` even though ``iter_rows()`` can still stream the worksheet XML.
    Reading both views as streams avoids relying on that optional metadata and
    also handles formula/data-only sheets with different row widths.
    """
    formula_rows = formula_sheet.iter_rows()
    value_rows = value_sheet.iter_rows()
    for row_no, (formula_row, value_row) in enumerate(
        zip_longest(formula_rows, value_rows, fillvalue=()), start=1
    ):
        yield row_no, formula_row, value_row
