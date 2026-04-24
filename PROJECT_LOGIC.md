# AnnotationCheck 项目逻辑梳理

## 1. 项目定位

`AnnotationCheck` 是一个基于 `PyQt5` 的桌面审查工具，用于多模态数据（可见光/红外图像 + 文本标注）的质检、编辑、标记与进度管理。  
核心目标是帮助审核人员高效发现文本问题、修正描述并沉淀审核结果。

---

## 2. 顶层结构与职责

- `main.py`：程序入口，初始化 Qt 运行环境并启动主窗口。
- `core/`：核心业务层（配置、序列加载、标注读写、规则校验、审核状态、图像解码、改写模型）。
- `ui/`：界面层（主窗口、图像区、文本区、导航、序列列表、问题列表、标记弹窗）。
- `config.json`：运行配置与会话状态（由 `core/config_manager.py` 管理）。
- `README.md`：使用说明与操作文档。
- `AnnotationCheck.spec`：PyInstaller 打包脚本。

---

## 3. 启动与初始化流程

### 3.1 启动入口

1. 运行 `main.py`。
2. `_setup_dll_paths()` 注入 Windows/Conda 下 Qt 相关 DLL 与插件路径。
3. 创建 `QApplication` 并实例化 `ui.main_window.MainWindow`。
4. 显示主窗口并进入 Qt 事件循环。

### 3.2 主窗口初始化

`MainWindow` 在初始化中完成以下动作：

1. 创建核心管理对象：
   - `ConfigManager`
   - `AnnotationManager`
   - `AnnotationValidator`
   - `ReviewManager`
2. 构建 UI 组件并绑定信号槽：
   - 序列列表（`SequencePanel`）
   - 图像面板（`ImagePanel`）
   - 文本面板（`TextPanel`）
   - 导航栏（`NavBar`）
   - 问题面板（`FlagPanel`）
3. 恢复上次会话状态（上次数据目录、序列、布局等）。
4. 启动自动保存定时器。
5. 首次配置场景下弹出 SDK 配置入口（翻译能力相关）。

---

## 4. 核心模块分工（Core）

## 4.1 `core/config_manager.py`

- 读写 `config.json`。
- 管理会话配置：最近数据目录、最近序列、布局参数、自动保存参数。
- 管理外部服务配置：翻译凭证与改写模型配置。

## 4.2 `core/sequence_loader.py`

- 从 `data/visual/` 扫描序列。
- 匹配 `visible/`、`infrared/` 图像路径。
- 关联 `data/text/{seq}.txt`。
- 输出 `SequenceInfo`（帧数、文本行数、差异信息等）。

## 4.3 `core/annotation_manager.py`

- 加载/维护当前序列文本行。
- 支持单行更新、全量替换、撤销重做。
- 执行保存：
  - 主文本落盘
  - 备份管理（数量上限）
  - 翻译缓存落盘

## 4.4 `core/annotation_validator.py`

- 对文本进行自动规则校验，输出 `Violation` 列表。
- 规则覆盖：
  - 词数超限
  - 相邻行重复或高相似
  - 中文字符与非法字符检查

## 4.5 `core/review_manager.py`

- 管理手动标记（如幻觉、语法、视觉不一致等）。
- 管理审核进度（按序列保存状态、最后位置、统计项）。
- 读写进度与标记 JSON 文件。

## 4.6 `core/image_loader.py`

- 使用 Pillow 解码图像并转为 `QPixmap`。
- 降低对 Qt 图像插件完整性的依赖，提升兼容性。

## 4.7 `core/paraphrase_model.py`

- 定义改写模型抽象接口 `AbstractParaphraseModel`。
- 提供模型工厂 `create_paraphrase_model(...)`。
- 当前支持：
  - `MiniMaxParaphraseModel`
  - `OpenAICompatParaphraseModel`

---

## 5. 界面模块分工（UI）

## 5.1 `ui/main_window.py`

- 应用控制中枢：组织数据加载、事件转发、状态同步、保存策略与后台任务管理。

## 5.2 `ui/text_panel.py`

- 当前帧文本编辑与整表展示。
- 支持跳帧、搜索、翻译触发。
- 翻译任务通过后台线程执行，结果回到主线程更新 UI。

## 5.3 `ui/image_panel.py`

- 展示可见光/红外图像。
- 支持缩放、平移、全屏与模式切换。
- 根据违规状态显示视觉反馈（如边框提示）。

## 5.4 `ui/nav_bar.py`

- 提供首尾/前后跳转、滑条定位、问题帧跳转、修改帧跳转。

## 5.5 `ui/sequence_panel.py`

- 展示序列列表与状态，负责序列切换入口。

## 5.6 `ui/flag_panel.py` 与 `ui/flag_dialog.py`

- 管理问题列表与手动标记交互。
- 支持筛选、跳转、导出、批量改写入口。

---

## 6. 主数据流与调用链

## 6.1 序列加载链路

1. 用户打开数据根目录。
2. `SequenceLoader` 扫描并构建序列信息。
3. 用户选择序列后：
   - `AnnotationManager` 加载文本
   - `ReviewManager` 加载该序列已有标记/进度
   - `AnnotationValidator` 计算违规列表
4. `MainWindow` 将结果同步到 `TextPanel`、`ImagePanel`、`FlagPanel`、`NavBar`。

## 6.2 编辑与校验链路

1. 用户在 `TextPanel` 编辑当前帧文本。
2. 通过信号回调到 `MainWindow`，写入 `AnnotationManager`。
3. 触发违规重算与界面刷新。
4. 按策略自动追加 `MODIFIED` 等标记信息。

## 6.3 保存与进度链路

- 手动保存：`AnnotationManager.save()`，含主文件与备份。
- 导航过程：可触发轻量保存（不一定生成备份）。
- 定时自动保存：由主窗口 `QTimer` 驱动。
- 序列级审核状态：由 `ReviewManager` 持久化。

---

## 7. 典型用户操作路径

1. 启动应用并打开数据目录。
2. 在序列列表中进入目标序列。
3. 浏览图像与文本，按帧定位问题。
4. 编辑文本并观察词数/违规反馈。
5. 对异常帧进行手动标记并添加备注。
6. 在问题列表筛选后复查并跳转修正。
7. 执行保存，必要时导出问题报告。
8. 关闭前自动保存并记录审核进度。

---

## 8. 配置与文件落盘说明

## 8.1 配置文件

- 文件：`config.json`
- 关键字段类型：
  - 会话状态（最近目录、最近序列）
  - UI 状态（布局模式、分割比例）
  - 自动保存开关与间隔
  - 翻译/改写模型相关凭证与参数

## 8.2 业务落盘

- 文本标注主文件：`data/text/*.txt`
- 备份文件：由 `AnnotationManager` 管理并轮转
- 审核标记与进度：JSON 文件（按序列维护）
- 翻译缓存：JSON 文件（按序列或模块缓存）

---

## 9. 当前实现中的关注点（维护建议）

1. `ui/flag_dialog.py` 中标记类型与展示文案映射需保持一致，避免新增类型后遗漏映射导致运行错误。
2. 自动保存是否创建备份应与文档保持一致，建议明确策略并统一实现。
3. 当前编辑后多处走全量校验，长序列下可能影响流畅度，可考虑增量校验。
4. 翻译与改写线程数量、速率限制和失败重试策略可进一步标准化。
5. 外部服务密钥目前位于本地配置，建议明确权限边界并考虑更安全的存储方式。
6. 统一日志与异常上报有助于定位线上问题，建议减少静默异常。

---

## 10. 一句话总结

该项目采用“`MainWindow` 统一调度 + `core` 业务解耦 + `ui` 组件协作”的结构，围绕“加载序列 -> 逐帧审查 -> 标注修正 -> 保存进度”形成完整闭环，适合在现有架构上继续扩展自动化质检与批量改写能力。
