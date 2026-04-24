# 基于 MiniMax 的自动复写与填充功能：实现链路与故障分析

本文面向当前代码实现，聚焦 `HALLUCINATION -> 批量改写 -> AI_GENERATED` 这条主链路，并分析常见运行时报错原因与修复思路。

---

## 1. 相关文件与职责

- `PROJECT_LOGIC.md`：项目总体逻辑说明（架构与主流程）。
- `ui/main_window.py`：批量改写入口、线程调度、结果写回与 UI 刷新。
- `ui/flag_panel.py`：问题列表、筛选、批量改写按钮。
- `core/review_manager.py`：标记数据读写，提供 `get_hallucination_indices()`。
- `core/paraphrase_model.py`：`MiniMaxParaphraseModel` / `OpenAICompatParaphraseModel` 接口实现。
- `core/config_manager.py`：模型类型与 API 配置读取/保存。
- `core/annotation_manager.py`：文本内容写回、修改态、落盘与备份。
- `ui/flag_dialog.py`：手动标记弹窗（与标记类型枚举强关联）。

---

## 2. 完整逻辑链路（端到端）

## 2.1 启动与配置阶段

1. `MainWindow` 初始化 `ConfigManager` / `AnnotationManager` / `ReviewManager` 等核心对象。
2. 用户在“配置 -> paraphrase 设置”中选择模型并保存：
   - `paraphrase_model`: `minimax` 或 `openai_compat`
   - `minimax_api_key` / `minimax_api_secret`
   - `openai_base_url` / `openai_api_key` / `openai_model`
3. 打开数据集并加载序列后，`ReviewManager.load_sequence()` 读取该序列已有标记。
4. `MainWindow._load_sequence()` 将 `review.get_hallucination_indices()` 注入到 `FlagPanel.set_pending_hallucination_indices()`，作为按钮触发批量改写的候选帧。

## 2.2 幻觉标记阶段

1. 用户通过 `Ctrl+F`（`_flag_as_hallucination`）或标记弹窗把当前帧标为 `HALLUCINATION`。
2. `ReviewManager.add_flag(frame_idx, "HALLUCINATION", note)` 持久化到 `review/{seq}_flags.json`。
3. `FlagPanel.refresh()` 重绘列表，显示标记项。

## 2.3 触发批量改写阶段

入口有两种：
- 按钮：`FlagPanel._request_bulk_rewrite()` 发 `bulk_rewrite_requested(list)`。
- 快捷键：`MainWindow._on_bulk_rewrite_shortcut()`，直接从 `ReviewManager` 取当前幻觉帧并确认。

主窗口处理：
1. `MainWindow._on_bulk_rewrite(hall_indices)` 校验前置条件（有序列、有索引、有 API key）。
2. 显示状态栏进度条。
3. 创建 `_RewriteThread`，传入：
   - 待改写帧列表 `hall_indices`
   - 模型配置 `model_config`
   - 当前文本 `ann_lines`
   - 当前帧标记快照 `review_flags`
4. 连接线程信号：
   - `progress(done, total, idx, para_text)` -> `_on_rewrite_progress`
   - `finished(done, total, error_msg)` -> `_on_rewrite_finished`

## 2.4 线程内“自动填充+改写”阶段

`_RewriteThread.run()` 的关键逻辑：

1. 根据 `model_type` 实例化模型：
   - `openai_compat` -> `OpenAICompatParaphraseModel`
   - 其他 -> `MiniMaxParaphraseModel`
2. 对每个 `idx` 执行 `find_ref(idx)`：
   - 从 `idx-1` 向前找最多 3 条参考文本；
   - 过滤 `HALLUCINATION` / `AI_GENERATED`；
   - 空行会停止继续向前搜索；
   - 返回按时间顺序参考列表 `caps`。
3. `model.paraphrase(caps)` 调用外部 API。
4. 取 `results[-1]` 作为当前目标帧的新文本（即“基于前文参考自动填充当前幻觉帧”）。
5. 发射 `progress` 信号回主线程。

## 2.5 主线程写回阶段

`_on_rewrite_progress`：
1. `ann_mgr.set_line(idx, para_text)` 写入新文本并置修改状态。
2. 删除原 `HALLUCINATION`，改写为 `AI_GENERATED`。
3. 更新进度条和侧边进度文案。

`_on_rewrite_finished`：
1. 隐藏进度条。
2. 重新全量校验 `validator.validate_all(...)`。
3. 刷新 `TextPanel`、`FlagPanel`、状态栏。
4. 若线程上报错误，弹窗提示失败帧。

---

## 3. 容易出错的原因与修复思路

以下为高概率导致“经常运行时报错或行为异常”的问题点。

## 3.1 标记弹窗可能直接崩溃（高优先级）

### 现象
- 打开标记弹窗时报 `KeyError: 'AI_GENERATED'`（或类似错误）。

### 根因
- `core/review_manager.py` 的 `FLAG_TYPES` 包含 `AI_GENERATED`。
- `ui/flag_dialog.py` 的 `labels` 字典未包含 `AI_GENERATED`，但构造时遍历 `FLAG_TYPES` 并直接 `labels[ftype]` 取值。

### 解决思路
- 方案 A（推荐）：在 `labels` 中补齐 `AI_GENERATED` 文案。
- 方案 B：构造按钮时使用 `labels.get(ftype, ftype)` 防御未知类型。
- 方案 C：将“可手动打标类型”与“系统自动标记类型”拆分，避免用户手动选择 `AI_GENERATED`。

---

## 3.2 批量按钮使用的幻觉列表可能过期（高优先级）

### 现象
- 新打的 `HALLUCINATION` 帧，点击“批量改写”按钮不生效；
- 或已改写完成后按钮仍试图处理旧帧。

### 根因
- `FlagPanel._pending_hall` 仅在 `_load_sequence()` 时注入一次；
- 后续标记变化（新增/删除/改写后替换标记）没有同步更新此缓存。

### 解决思路
- 每次按钮点击时实时从 `review.get_hallucination_indices()` 拉取，而不是依赖缓存；
- 或在每次 `_refresh_flag_panel()` 后同步 `set_pending_hallucination_indices(...)`。

---

## 3.3 线程参考标记快照不完整，可能误选参考帧（中高优先级）

### 现象
- 某些帧改写质量异常，参考文本看起来不对；
- 连续幻觉段落中，理论应跳过的帧可能被误用。

### 根因
- 线程里 `review_flags` 只构建了 `hall_indices` 的子集映射；
- `find_ref` 查前序帧时若候选帧不在该映射中，默认 `None`，无法准确判断其真实标记类型。

### 解决思路
- 传入完整 `review.all_flags()` 给线程；
- 或让线程只接收“可用参考索引集合”，避免在线程内访问不完整标记状态。

---

## 3.4 配置校验不足导致“看似执行但全失败”（高优先级）

### 现象
- 点击批量改写后进度走不动/大量失败；
- 日志显示认证失败、URL 错误或断言异常。

### 根因
- 当前只校验“是否存在任意一个 key”：
  - 选 `minimax` 时没强校验 `api_secret`；
  - 选 `openai_compat` 时没强校验 `base_url` / `api_key` / `model`。

### 解决思路
- 按模型类型做严格前置校验并弹明确错误：
  - `minimax`: key+secret 必填；
  - `openai_compat`: base_url+api_key+model 必填。
- 在配置对话框 `OK` 前进行必填校验，减少运行时失败。

---

## 3.5 API 返回格式兼容性不足（中优先级）

### 现象
- 偶发解析失败，`results=[]`；
- 服务端有返回但客户端解析不到内容。

### 根因
- `MiniMaxParaphraseModel` 对 `choices/messages/text` 结构假设较强；
- 不同模型/版本响应结构差异导致解析路径失效。

### 解决思路
- 增加多路径容错解析（如 `message.content`、`output_text` 等候选字段）；
- 记录原始响应摘要到日志（脱敏）；
- 若响应为空，返回可读错误码而非仅 `[]`。

---

## 3.6 失败重试与限流缺失（中优先级）

### 现象
- 网络抖动时批量任务失败率高；
- 大批量时可能触发服务端限频。

### 根因
- 每帧单次请求，无重试、无退避、无限速控制。

### 解决思路
- 增加最多 2~3 次重试（指数退避）；
- 在批量线程中加轻量节流（如每次请求间隔 100~300ms，可配置）；
- 统计失败类型（超时/401/429/5xx）做分类提示。

---

## 3.7 线程与主线程共享可变数据，存在竞态风险（中优先级）

### 现象
- 极端情况下改写结果与当前编辑冲突；
- 偶发“改写覆盖了用户刚编辑内容”。

### 根因
- `_RewriteThread` 直接持有 `ann_mgr.lines` 引用；
- 用户在批量执行期间仍可编辑/切帧，主线程与子线程读写同一数据源。

### 解决思路
- 启动线程前拷贝只读快照（`list(self.ann_mgr.lines)`）；
- 批量执行期间临时禁用编辑控件；
- 写回时可增加“冲突检测”（若用户已改动则跳过并提示）。

---

## 3.8 参考文本搜索策略过于激进（中优先级）

### 现象
- 前面某一帧为空行时，后续帧即使再往前有可用文本也被跳过。

### 根因
- `find_ref` 遇到空文本直接 `break`，停止继续向前搜索。

### 解决思路
- 改为 `continue` 跳过空行，继续向前查找；
- 最多向前扫描窗口长度可配（如 20 帧）。

---

## 3.9 错误可观测性不足，排障成本高（中优先级）

### 现象
- 用户只看到“某帧失败”，但不清楚失败原因和具体请求状态。

### 根因
- 大量异常仅 `print`，UI 仅汇总简要错误；
- 部分核心存储/配置异常被静默吞掉（如 `ConfigManager.save`、`AnnotationManager.save_translations`）。

### 解决思路
- 增加统一日志模块（按天落盘）；
- 区分用户提示与开发日志：UI 显示简短错误，日志保留异常栈与上下文；
- 对关键写文件失败至少给出一次弹窗或状态栏告警。

---

## 4. 建议的修复优先级（可执行）

### P0（立即）
- 修复 `FlagDialog` 的 `AI_GENERATED` 映射缺失。
- 批量改写前按模型类型做完整配置校验。
- 批量按钮改为实时读取 `review.get_hallucination_indices()`。

### P1（本周）
- 线程改用数据快照，执行期间禁用编辑避免竞态。
- 完整传递/计算参考帧过滤条件，修正 `find_ref` 逻辑。
- 改善 API 响应解析容错与错误信息上报。

### P2（后续稳定性）
- 增加重试、退避、限流。
- 建立统一日志与失败分类统计。
- 用增量校验替代全量校验优化大序列性能。

---

## 5. 一句话总结

当前功能链路已经形成闭环（标记 -> 批量改写 -> 写回 -> 复检），但运行时不稳定的核心原因在于：**类型映射缺口、配置校验不足、状态缓存过期、线程共享状态与错误可观测性弱**。优先修复 P0/P1 项后，批量改写稳定性会显著提升。
