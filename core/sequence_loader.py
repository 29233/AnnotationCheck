from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

import natsort


@dataclass
class SequenceInfo:
    name: str
    visible_paths: List[str]
    infrared_paths: List[str]
    text_path: Optional[str]
    frame_count: int
    text_line_count: int = 0       # actual lines in txt (0 if no file)

    @property
    def has_text(self) -> bool:
        return self.text_path is not None

    @property
    def line_frame_diff(self) -> int:
        return self.text_line_count - self.frame_count


_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


class SequenceLoader:
    def __init__(self, data_root: str):
        self.data_root = Path(data_root).resolve()   # always absolute
        self.visual_root = self.data_root / "visual"
        self.text_root = self.data_root / "text"

    # ------------------------------------------------------------------
    def list_sequences(self) -> List[str]:
        if not self.visual_root.exists():
            return []
        names = [d.name for d in self.visual_root.iterdir() if d.is_dir()]
        return natsort.natsorted(names)

    # ------------------------------------------------------------------
    def load_sequence(self, seq_name: str) -> SequenceInfo:
        seq_root = self.visual_root / seq_name / seq_name

        visible_paths = self._img_files(seq_root / "visible")
        infrared_paths = self._img_files(seq_root / "infrared")

        text_path_obj = self.text_root / f"{seq_name}.txt"
        text_path = str(text_path_obj) if text_path_obj.exists() else None

        text_line_count = 0
        if text_path:
            with open(text_path, "r", encoding="utf-8") as f:
                text_line_count = len(f.read().splitlines())

        frame_count = max(len(visible_paths), len(infrared_paths))

        return SequenceInfo(
            name=seq_name,
            visible_paths=visible_paths,
            infrared_paths=infrared_paths,
            text_path=text_path,
            frame_count=frame_count,
            text_line_count=text_line_count,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _img_files(directory: Path) -> List[str]:
        if not directory.exists():
            return []
        files = [str(p) for p in directory.iterdir() if p.suffix.lower() in _IMG_EXTS]
        return natsort.natsorted(files)
