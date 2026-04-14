import re
import difflib
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class Violation:
    frame_idx: int
    vtype: str      # OVER_LIMIT | OVER_WARN | DUPLICATE | SIMILAR | MIXED_LANG
    severity: str   # error | warning
    detail: str


_MIXED_RE = re.compile(r"[\u4e00-\u9fff\uff00-\uffef\x00-\x08\x0b\x0c\x0e-\x1f]")

WORD_WARN = 20
WORD_LIMIT = 30
SIMILAR_THRESHOLD = 0.90


class AnnotationValidator:
    def validate_all(self, lines: List[str]) -> Dict[int, List[Violation]]:
        result: Dict[int, List[Violation]] = {}
        for i in range(len(lines)):
            viols = self._check(i, lines)
            if viols:
                result[i] = viols
        return result

    def validate_range(self, idx: int, lines: List[str]) -> Dict[int, List[Violation]]:
        """Re-validate idx and its two neighbors (for incremental update after edit)."""
        result: Dict[int, List[Violation]] = {}
        for i in [idx - 1, idx, idx + 1]:
            if 0 <= i < len(lines):
                viols = self._check(i, lines)
                result[i] = viols   # always set, even empty list
        return result

    def _check(self, idx: int, lines: List[str]) -> List[Violation]:
        line = lines[idx]
        viols: List[Violation] = []

        # 1. word count
        wc = len(line.split())
        if wc > WORD_LIMIT:
            viols.append(Violation(idx, "OVER_LIMIT", "error",
                                   f"{wc} words (absolute limit: {WORD_LIMIT})"))
        elif wc > WORD_WARN:
            viols.append(Violation(idx, "OVER_WARN", "warning",
                                   f"{wc} words (suggest ≤{WORD_WARN})"))

        # 2. mixed language / garbled chars
        if _MIXED_RE.search(line):
            viols.append(Violation(idx, "MIXED_LANG", "error",
                                   "Contains Chinese or illegal characters"))

        # 3. adjacent duplicate / high similarity (check prev and next)
        dup_found = False
        for ni in [idx - 1, idx + 1]:
            if dup_found:
                break
            if 0 <= ni < len(lines):
                nb = lines[ni]
                if line == nb:
                    viols.append(Violation(idx, "DUPLICATE", "error",
                                           f"Identical to frame {ni + 1}"))
                    dup_found = True
                else:
                    ratio = difflib.SequenceMatcher(None, line, nb).ratio()
                    if ratio >= SIMILAR_THRESHOLD:
                        viols.append(Violation(idx, "SIMILAR", "warning",
                                               f"{ratio:.0%} similar to frame {ni + 1}"))
                        dup_found = True

        return viols
