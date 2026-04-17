from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QRadioButton, QLineEdit, QPushButton, QButtonGroup,
                              QGroupBox)
from core.review_manager import FLAG_TYPES


class FlagDialog(QDialog):
    """标记帧问题类型选择框"""

    def __init__(self, frame_idx: int, existing: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"标记帧 {frame_idx + 1}")
        self.setMinimumWidth(400)
        self._result_type = None
        self._result_note = ""

        existing = existing or {}

        # ── 问题类型 ─────────────────────────────────────
        group_box = QGroupBox("问题类型")
        btn_layout = QVBoxLayout(group_box)
        self._btn_group = QButtonGroup(self)

        labels = {
            "HALLUCINATION": "幻觉（HALLUCINATION）—— 描述了图像中不存在的内容",
            "GRAMMAR":       "语法错误（GRAMMAR）—— 拼写 / 时态 / 冠词错误",
            "VISUAL":        "视觉不准确（VISUAL）—— 目标 / 颜色 / 动作与图像不符",
            "OTHER":         "其他（OTHER）",
            "MODIFIED":      "已修改（MODIFIED）—— 文本已被手动编辑",
            "AI_GENERATED":  "AI改写（AI_GENERATED）—— 文本由批量改写生成",
        }
        for i, ftype in enumerate(FLAG_TYPES):
            rb = QRadioButton(labels.get(ftype, f"{ftype}（未配置文案）"))
            rb.setProperty("flag_type", ftype)
            self._btn_group.addButton(rb, i)
            btn_layout.addWidget(rb)
            if existing.get("type") == ftype:
                rb.setChecked(True)
        if not existing:
            self._btn_group.button(0).setChecked(True)

        # ── 备注 ────────────────────────────────────────────
        note_label = QLabel("备注（可选）：")
        self._note_input = QLineEdit(existing.get("note", ""))

        # ── 按钮 ─────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_ok     = QPushButton("标记")
        self._btn_remove = QPushButton("取消标记")
        self._btn_cancel = QPushButton("取消")
        self._btn_remove.setEnabled(bool(existing))
        btn_row.addWidget(self._btn_ok)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(group_box)
        layout.addWidget(note_label)
        layout.addWidget(self._note_input)
        layout.addLayout(btn_row)

        self._btn_ok.clicked.connect(self._accept)
        self._btn_remove.clicked.connect(self._remove)
        self._btn_cancel.clicked.connect(self.reject)

    # ── results ─────────────────────────────────────────────
    @property
    def flag_type(self):
        return self._result_type

    @property
    def note(self):
        return self._result_note

    @property
    def removed(self):
        return self._result_type == "__REMOVE__"

    def _accept(self):
        btn = self._btn_group.checkedButton()
        if btn:
            self._result_type = btn.property("flag_type")
        self._result_note = self._note_input.text().strip()
        self.accept()

    def _remove(self):
        self._result_type = "__REMOVE__"
        self.accept()