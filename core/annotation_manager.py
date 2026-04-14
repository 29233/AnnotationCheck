import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict


class AnnotationManager:
    MAX_UNDO = 50
    MAX_BACKUPS = 10

    def __init__(self):
        self.lines: List[str] = []
        self._undo_stack: List[List[str]] = []
        self._redo_stack: List[List[str]] = []
        self._text_path: Optional[str] = None
        self._modified = False

        # ── translation persistence ─────────────────────────────────────
        self._translations: Dict[int, str] = {}   # frame_idx → translated text
        self._translations_path: Optional[Path] = None

    # ------------------------------------------------------------------ load/save
    def load(self, path: str):
        self._text_path = path
        with open(path, "r", encoding="utf-8") as f:
            self.lines = f.read().splitlines()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._modified = False
        self.load_translations()

    def clear(self):
        self.save_translations()
        self.lines = []
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._text_path = None
        self._modified = False
        self._translations.clear()

    # ── translation persistence ─────────────────────────────────────────
    def _init_translations_path(self):
        """Initialise the translations file path from the current text path."""
        if not self._text_path:
            self._translations_path = None
            return
        text_path = Path(self._text_path)
        # data/text/translations/seq_name_translations.json
        trans_dir = text_path.parent.parent / "translations"
        trans_dir.mkdir(parents=True, exist_ok=True)
        self._translations_path = trans_dir / f"{text_path.stem}_translations.json"

    def load_translations(self):
        """Load cached translations from disk for the current sequence."""
        self._init_translations_path()
        if not self._translations_path or not self._translations_path.exists():
            self._translations.clear()
            return
        try:
            with open(self._translations_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # data structure: {str_idx: {"text": "...", "src_lang": "en", "tgt_lang": "zh", "annotation": "..."}}
            self._translations.clear()
            for str_idx, entry in data.items():
                self._translations[int(str_idx)] = entry.get("text", "")
        except Exception:
            self._translations.clear()

    def save_translations(self):
        """Save current translations cache to disk."""
        if not self._translations_path:
            return
        try:
            self._translations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._translations_path, "w", encoding="utf-8") as f:
                json.dump(self._translations, f, ensure_ascii=False, indent=2)
        except Exception:
            pass   # non-critical, swallow errors silently

    def get_translation(self, idx: int) -> Optional[str]:
        """Return cached translation for frame idx, or None if not cached."""
        return self._translations.get(idx)

    def set_translation(self, idx: int, text: str):
        """Cache a translation result in memory (saved to disk by save_translations)."""
        self._translations[idx] = text

    @property
    def translations(self) -> Dict[int, str]:
        """Direct access to the translations dict (for iteration/lookup)."""
        return self._translations

    def save(self) -> bool:
        if not self._text_path:
            return False
        content = "\n".join(self.lines)
        with open(self._text_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        self._create_backup(content)
        self._modified = False
        self.save_translations()
        return True

    def _create_backup(self, content: str):
        path = Path(self._text_path)
        backup_dir = path.parent / "backup" / path.stem
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{path.stem}_{ts}.txt"
        with open(backup_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        # keep only MAX_BACKUPS
        backups = sorted(backup_dir.iterdir(), key=lambda p: p.name)
        while len(backups) > self.MAX_BACKUPS:
            backups[0].unlink()
            backups = backups[1:]

    # ------------------------------------------------------------------ edit ops
    def set_line(self, idx: int, text: str):
        self._push_undo()
        self.lines[idx] = text
        self._mark_modified()

    def insert_line_after(self, idx: int, text: str = ""):
        self._push_undo()
        self.lines.insert(idx + 1, text)
        self._mark_modified()

    def insert_line_before(self, idx: int, text: str = ""):
        self._push_undo()
        self.lines.insert(idx, text)
        self._mark_modified()

    def delete_line(self, idx: int):
        self._push_undo()
        self.lines.pop(idx)
        self._mark_modified()

    def set_all_lines(self, lines: List[str]):
        """Replace all lines at once (used after full-text edit)."""
        self._push_undo()
        self.lines = list(lines)
        self._mark_modified()

    # ------------------------------------------------------------------ undo/redo
    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(list(self.lines))
        self.lines = self._undo_stack.pop()
        self._modified = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(list(self.lines))
        self.lines = self._redo_stack.pop()
        self._modified = True
        return True

    # ------------------------------------------------------------------ helpers
    def _push_undo(self):
        self._undo_stack.append(list(self.lines))
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)

    def _mark_modified(self):
        self._modified = True
        self._redo_stack.clear()

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def text_path(self) -> Optional[str]:
        return self._text_path

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
