# 批量 AI 改写功能 — 技术设计文档

> 本文档描述三个新功能的完整实现方案：快捷键标记、筛选机制、批量 AI 改写。
> paraphrase 要求待用户提供后补充最后一部分。

---

## 功能一：Ctrl+F 直接标记为幻觉

### 目标
按 `Ctrl+F` ，无需弹窗确认，直接将当前帧标记为 HALLUCINATION。

### 修改文件

**`ui/main_window.py`**

在 `_build_shortcuts()` 中新增快捷键绑定：

```python
sc("Ctrl+F", self._flag_as_hallucination)
```

新增实例方法：

```python
def _flag_as_hallucination(self):
    """将当前帧直接标记为 HALLUCINATION（无需弹窗）。"""
    if not (self.review and self.seq_info):
        return
    idx = self._current_frame
    existing = self.review.get_flag(idx) or {}
    # 已是 HALLUCINATION 则跳过
    if existing.get("type") == "HALLUCINATION":
        return
    # 覆盖任何已有标记类型，写入新标记
    self.review.add_flag(idx, "HALLUCINATION", "")
    self._refresh_flag_panel()
    self._update_status_bar()
    self._flash_saved("已标记为幻觉")
```

### 行为说明

| 情况 | 行为 |
|------|------|
| 当前帧无任何标记 | 新增 HALLUCINATION 标记 |
| 当前帧已有其他类型标记（GRAMMAR / VISUAL / OTHER / MODIFIED） | 覆盖为 HALLUCINATION |
| 当前帧已是 HALLUCINATION | 无操作（防止重复写入文件） |
| 未加载序列（无 review / seq_info） | 无操作 |

---

## 功能二：按标记类型筛选帧

### 目标

在问题列表面板顶部增加筛选 CheckBox，允许用户只看某一类或某几类问题帧。双击条目时同样跳转到对应帧。

### 修改文件

**`ui/flag_panel.py`**

#### 新增 UI 元素

在 `_list` 上方新增筛选控制行（QHBoxLayout）：

```
[筛选：] [□幻觉] [□语法] [□视觉] [□其他] [□已修改]  │  [□错误] [□警告]  [重置]
```

#### 新增属性

```python
self._active_filters: Set[str] = set()   # 当前激活的筛选类型集合
```

#### 新增信号

```python
filter_changed = pyqtSignal(set)   # 发出当前激活的筛选类型集合
```

#### `_rebuild()` 修改逻辑

```python
def _rebuild(self):
    self._list.clear()

    # ── 合并手动 + 自动 ───────────────────────────────
    all_items = []   # (idx, sort_key, display_text, color)

    # 手动标记
    for idx in sorted(self._manual.keys()):
        info = self._manual[idx]
        ftype = info.get("type", "OTHER")
        # 筛选逻辑
        if self._active_filters and ftype not in self._active_filters:
            continue
        ...

    # 自动违规
    for idx in sorted(self._auto_violations.keys()):
        viols = self._auto_violations[idx]
        top = max(viols, key=lambda v: v.severity == "error")
        # 筛选逻辑：
        #   若激活了 "错误" → 显示 severity==error 的项
        #   若激活了 "警告" → 显示 severity==warning 的项
        #   精确类型覆盖以上两类（精确类型优先）
        ...

    if not all_items:
        item = QListWidgetItem("  （无匹配项）")
        item.setFlags(Qt.NoItemFlags)
        self._list.addItem(item)

    # 更新标题计数
    total = len(all_items)
    self._lbl_title.setText(f"<b>问题列表（{total}）</b>")
```

#### 筛选 CheckBox 逻辑

```python
def _on_filter_changed(self):
    """收集所有选中的 CheckBox 类型，构建 active_filters 集合并刷新列表。"""
    filters = set()
    for ftype, cb in self._filter_checkboxes.items():
        if cb.isChecked():
            filters.add(ftype)
    self._active_filters = filters
    self.filter_changed.emit(filters)
    self._rebuild()
```

#### 新增方法

```python
def reset_filters(self):
    """全不选 = 显示全部（现有行为）。"""
    for cb in self._filter_checkboxes.values():
        cb.setChecked(False)
    self._on_filter_changed()
```

---

**`ui/main_window.py`**

新增连接：

```python
self.flag_panel.filter_changed.connect(self._on_flag_filter_changed)
```

新增实例属性（初始化）：

```python
self._active_flag_filters: set = set()
```

新增方法：

```python
def _on_flag_filter_changed(self, filters: set):
    """收到筛选变化时更新导航过滤集合。"""
    self._active_flag_filters = filters
```

修改 `_prev_flag()` / `_next_flag()` / `_prev_violation()` / `_next_violation()`：

```python
def _get_filtered_flags(self) -> List[int]:
    """返回当前激活筛选条件下的问题帧列表（升序）。"""
    all_flags = set(self.review.flagged_indices())
    if not self._active_flag_filters:
        return sorted(all_flags)
    # 仅保留类型匹配的帧
    filtered = set()
    for idx in all_flags:
        flag = self.review.get_flag(idx) or {}
        if flag.get("type") in self._active_flag_filters:
            filtered.add(idx)
    return sorted(filtered)
```

原有导航方法改为调用 `_get_filtered_flags()` 而非直接用 `self.review.flagged_indices()`。

---

## 功能三：批量 AI 改写

### 目标

对所有被标记为 HALLUCINATION 的帧，将标注文本替换为参考文本的 paraphrase 结果，并移除其 HALLUCINATION 标记。

### 核心流程

```
触发（按钮 / Ctrl+R）
  → ReviewManager.get_hallucination_indices()
       返回所有 HALLUCINATION 帧号列表
  → 对每个待改写帧 idx:
       ref_idx = 找最近的无 HALLUCINATION 标记的前帧
       ref_text = ann_mgr.lines[ref_idx]
       para_text = paraphrase(ref_text)
       ann_mgr.set_line(idx, para_text)
       review.remove_flag(idx)       # 改写后移除幻觉标记
  → validator.validate_all()        # 重新验证
  → text_panel.reload_all()         # 刷新 UI
  → status_bar 更新
```

### 优先级说明

每个 HALLUCINATION 帧的参考文本取**最近的前帧**（不含 HALLUCINATION 标记）：
- 第 0 帧无法改写（无参考）→ 跳过
- 前帧也是 HALLUCINATION → 继续往前找
- 找到首个非 HALLUCINATION 前帧 → 作为 paraphrase 源文本

### 修改文件

**`core/review_manager.py`**

新增方法：

```python
def get_hallucination_indices(self) -> List[int]:
    """返回所有被标记为 HALLUCINATION 的帧号（按帧号升序）。"""
    return sorted([
        int(k) for k, v in self._flags.items()
        if v.get("type") == "HALLUCINATION"
    ])
```

**`ui/flag_panel.py`**

新增按钮（底部按钮行）：

```python
self._btn_bulk_rewrite = QPushButton("批量改写")
self._btn_bulk_rewrite.setFixedWidth(100)
self._lbl_rewrite_progress = QLabel("")

btn_row.addWidget(self._btn_bulk_rewrite)
btn_row.addWidget(self._lbl_rewrite_progress)
btn_row.addStretch()

self._btn_bulk_rewrite.clicked.connect(self._request_bulk_rewrite)
```

新增信号：

```python
bulk_rewrite_requested = pyqtSignal(list)   # 发出待改写的帧号列表
```

新增方法：

```python
def _request_bulk_rewrite(self):
    hall_indices = self._get_hallucination_indices_for_rewrite()
    if not hall_indices:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "无内容", "当前序列中没有幻觉标记的帧。")
        return
    self.bulk_rewrite_requested.emit(hall_indices)

def _get_hallucination_indices_for_rewrite(self) -> List[int]:
    """返回可以改写的 HALLUCINATION 帧号列表（有有效参考文本）。"""
    if not hasattr(self._parent_or_main, 'review'):
        return []
    hall_indices = self._parent_or_main.review.get_hallucination_indices()
    result = []
    for idx in hall_indices:
        ref_idx = self._find_reference_frame(idx)
        if ref_idx is not None:
            result.append(idx)
    return result

def _find_reference_frame(self, idx: int) -> Optional[int]:
    """从 idx-1 向前找最近的无 HALLUCINATION 前帧。无参考则返回 None。"""
    if not hasattr(self._parent_or_main, 'review'):
        return None
    for candidate in range(idx - 1, -1, -1):
        flag = self._parent_or_main.review.get_flag(candidate)
        if not flag or flag.get("type") != "HALLUCINATION":
            return candidate
    return None
```

**`ui/main_window.py`**

新增连接：

```python
self.flag_panel.bulk_rewrite_requested.connect(self._on_bulk_rewrite)
```

新增快捷键：

```python
sc("Ctrl+R", self._on_bulk_rewrite_shortcut)
```

新增方法：

```python
def _on_bulk_rewrite_shortcut(self):
    """快捷键 Ctrl+R：触发批量改写流程（对话框确认）。"""
    if not self.review:
        return
    hall_indices = self.review.get_hallucination_indices()
    if not hall_indices:
        return
    from PyQt5.QtWidgets import QMessageBox
    resp = QMessageBox.question(
        self, "批量改写",
        f"将对 {len(hall_indices)} 个幻觉帧执行 paraphrase 改写。\n"
        "改写后 HALLUCINATION 标记将被移除。\n\n是否继续？",
        QMessageBox.Yes | QMessageBox.No)
    if resp == QMessageBox.Yes:
        self._on_bulk_rewrite(hall_indices)
```

新增 `_on_bulk_rewrite(frame_indices: List[int])`：

```python
def _on_bulk_rewrite(self, frame_indices: List[int]):
    """执行批量 paraphrase 改写。"""
    if not self.ann_mgr or not self.seq_info:
        return

    ref_texts = {}   # idx → reference text

    # 第一步：收集每个待改写帧的参考文本
    for idx in frame_indices:
        ref_idx = self._find_reference_for_hallucination(idx)
        if ref_idx is None:
            print(f"[批量改写] 帧 {idx} 无有效参考文本，跳过")
            continue
        ref_texts[idx] = self.ann_mgr.lines[ref_idx]

    if not ref_texts:
        QMessageBox.warning(self, "无可改写内容",
                           "所有幻觉帧均无有效参考文本。")
        return

    total = len(ref_texts)
    self._bulk_rewrite_progress = 0

    def update_progress(done):
        self._bulk_rewrite_progress += 1
        self.flag_panel.update_rewrite_progress(
            self._bulk_rewrite_progress, total)

    # 第二步：对每个帧执行 paraphrase 并写入
    for idx, ref_text in ref_texts.items():
        para_text = paraphrase_text(ref_text)   # ← 调用 AI paraphrase
        if para_text:
            self.ann_mgr.set_line(idx, para_text)
            self.review.remove_flag(idx)         # 移除幻觉标记
            self.ann_mgr._modified = True
        update_progress(1)

    # 第三步：重新验证并刷新 UI
    self._violations = self.validator.validate_all(self.ann_mgr.lines)
    self._cache_violation_indices(self._violations)
    self.text_panel.reload_all(self.ann_mgr.lines, self._violations)
    self._refresh_flag_panel()
    self._update_status_bar()
    self._flash_saved(f"批量改写完成（{len(ref_texts)} 帧）")

def _find_reference_for_hallucination(self, idx: int) -> Optional[int]:
    """从 idx-1 向前找最近的无 HALLUCINATION 标记的前帧。"""
    for candidate in range(idx - 1, -1, -1):
        flag = self.review.get_flag(candidate)
        if not flag or flag.get("type") != "HALLUCINATION":
            return candidate
    return None
```

### Paraphrase 接口（TODO — 待用户提供参数）

```python
# paraphrase_api.py 或内嵌于 main_window.py

def paraphrase_text(text: str) -> Optional[str]:
    """
    调用 AI paraphrase 接口对 text 进行改写。

    TODO（用户补充以下信息后实现）：
      1. 使用哪个 API（阿里云 / OpenAI / 本地模型）
      2. API 端点、模型名称、认证方式
      3. 调用参数（temperature、max_tokens 等）
      4. 是否需保留语言方向（英→英 / 中→英）
      5. 批量处理时是否需逐条确认

    当前返回 None（占位），实现后替换为真实 API 调用。
    """
    raise NotImplementedError(
        "paraphrase API 参数待用户提供，请补充："
        "1) API 类型（阿里云/OpenAI/本地）"
        "2) 端点 URL"
        "3) 模型名称"
        "4) 认证方式（API Key / Access Key）"
        "5) 语言方向要求"
    )
```

---

## 文件修改总览

| 文件 | 修改内容 |
|------|---------|
| `ui/main_window.py` | `Ctrl+F` → `_flag_as_hallucination()`；`Ctrl+R` → `_on_bulk_rewrite()`；`_prev_flag()` / `_next_flag()` 接入筛选逻辑；新增 `_on_flag_filter_changed()` / `_find_reference_for_hallucination()` |
| `ui/flag_panel.py` | 筛选 CheckBox 行；`filter_changed` 信号；`_active_filters` 属性；`_btn_bulk_rewrite` + `_bulk_rewrite_requested` 信号；`reset_filters()` 方法 |
| `core/review_manager.py` | 新增 `get_hallucination_indices()` |

---

## 待用户提供的信息

1. **paraphrase API**：使用哪个服务商（阿里云 / OpenAI / 其他）？
2. **端点 URL**：API 的 HTTPS 地址
3. **认证方式**：API Key / Access Key Secret / 其他
4. **模型名称**：具体使用哪个模型（如 `qwen-7b`、`gpt-4o-mini` 等）
5. **语言方向**：输入英文输出英文（英→英），还是中文参考输出英文？
6. **确认机制**：批量改写每条是否需要弹窗确认？还是直接执行？

---

## 实现顺序建议

```
Step 1 → 功能一（Ctrl+F 标记）+ 功能二（筛选）
         ↓
Step 2 → paraphrase 接口对接
         ↓
Step 3 → 功能三（批量改写按钮 + Ctrl+R）
```

Step 1 可独立交付，Step 2 / 3 取决于 paraphrase 需求的明确程度。
