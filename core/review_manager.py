import json
from pathlib import Path
from datetime import date
from typing import Optional, Dict, Any


FLAG_TYPES = ["HALLUCINATION", "GRAMMAR", "VISUAL", "OTHER", "MODIFIED"]
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"


class ReviewManager:
    def __init__(self, data_root: str):
        self._review_dir = Path(data_root) / "review"
        self._review_dir.mkdir(parents=True, exist_ok=True)
        self._progress_path = self._review_dir / "progress.json"
        self._progress: Dict[str, Any] = self._load_json(self._progress_path)
        self._seq_name: Optional[str] = None
        self._flags: Dict[str, Any] = {}   # frame_idx(str) -> {type, note}
        self._flags_path: Optional[Path] = None

    # ------------------------------------------------------------------ sequence
    def load_sequence(self, seq_name: str):
        self._seq_name = seq_name
        self._flags_path = self._review_dir / f"{seq_name}_flags.json"
        raw = self._load_json(self._flags_path)
        self._flags = raw.get("flagged_frames", {})

    # ------------------------------------------------------------------ flags
    def add_flag(self, frame_idx: int, flag_type: str, note: str = ""):
        key = str(frame_idx)
        self._flags[key] = {"type": flag_type, "note": note}
        self._save_flags()

    def remove_flag(self, frame_idx: int):
        key = str(frame_idx)
        if key in self._flags:
            del self._flags[key]
            self._save_flags()

    def get_flag(self, frame_idx: int) -> Optional[Dict]:
        return self._flags.get(str(frame_idx))

    def all_flags(self) -> Dict[int, Dict]:
        return {int(k): v for k, v in self._flags.items()}

    def flagged_indices(self):
        return sorted(int(k) for k in self._flags)

    # ------------------------------------------------------------------ progress
    def get_progress(self, seq_name: str) -> Dict:
        return self._progress.get(seq_name, {})

    def update_progress(self, seq_name: str, status: str, last_frame: int,
                        violation_count: int = 0, manual_flag_count: int = 0):
        entry = self._progress.get(seq_name, {})
        entry["status"] = status
        entry["last_frame"] = last_frame
        entry["violation_count"] = violation_count
        entry["manual_flag_count"] = manual_flag_count
        if status == STATUS_DONE:
            entry["reviewed_at"] = date.today().isoformat()
        self._progress[seq_name] = entry
        self._save_json(self._progress_path, self._progress)

    def all_progress(self) -> Dict[str, Dict]:
        return dict(self._progress)

    # ------------------------------------------------------------------ helpers
    def _save_flags(self):
        if self._flags_path:
            self._save_json(self._flags_path, {"flagged_frames": self._flags})

    @staticmethod
    def _load_json(path: Path) -> Dict:
        if path and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def _save_json(path: Path, data: Dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
