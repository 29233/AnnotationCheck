# Paraphrase Model 模块详解

## 概述

`core/paraphrase_model.py` 实现了一个基于 API 的 paraphrase（改写）功能接口层，支持 MiniMax 和 OpenAI 兼容接口两种实现。

---

## 架构

```
AbstractParaphraseModel (抽象基类)
├── MiniMaxParaphraseModel       (@register_model("minimax"))
└── OpenAICompatParaphraseModel  (@register_model("openai_compat"))
```

通过 `PARAPHRASE_MODELS` 注册表选择模型，默认 `minimax`。

---

## 公共接口

### `AbstractParaphraseModel.paraphrase(captions: List[str]) -> List[str]`

| 参数 | 类型 | 说明 |
|------|------|------|
| `captions` | `List[str]` | 1~3 条参考标注（按时间顺序） |

| 返回值 | 说明 |
|--------|------|
| `List[str]` | 一句 paraphrase 结果（列表形式） |
| `[]` | API 调用失败或超时时返回空列表 |

---

## 系统提示词（SYSTEM_PROMPT）

两个模型共享同一个 `SYSTEM_PROMPT`：

```
You are a professional image captioning assistant.
Your task is to generate a single paraphrase based on reference captions
while strictly following these rules:
1. Preserve the MAIN SUBJECT of the scene (person, vehicle, animal, object, etc.)
   — do NOT change, add, or remove the subject. The subject must remain identical.
2. ONLY rephrase the wording to achieve diversity — do not generate any content
   that is not already present in any of the reference captions.
3. Keep the description factual and grounded in the image —
   do NOT add actions, attributes, or details not supported by the references.
4. Output ONLY the paraphrased caption text, ONE single sentence.
   Do NOT include any explanation, reasoning, quotation marks, numbering, or labels.
   Only output the bare paraphrased sentence, nothing else.
5. The input contains 1–3 reference captions from the same video sequence.
   Integrate their information into ONE coherent paraphrase, keeping the same subject and tense.
```

---

## MiniMaxParaphraseModel

### 类定义

```python
@register_model("minimax")
class MiniMaxParaphraseModel(AbstractParaphraseModel):
    def __init__(self, api_key: str = "", api_secret: str = "",
                 model: str = "abab6.5s-chat", timeout: int = 30):
```

### 完整输入输出

#### `paraphrase()` 输入

**参数：**
- `captions: List[str]` — 1~3 条参考标注

**构建的 Payload：**

```python
payload = {
    "model": "abab6.5s-chat",           # 可配置，默认 "abab6.5s-chat"
    "messages": [
        {
            "role": "system",
            "content": SYSTEM_PROMPT      # 见上文
        },
        {
            "role": "user",
            "content": "Please generate one paraphrase based on the following reference captions:\n\n"
                       "[Reference 1]: <captions[0]>\n"
                       "[Reference 2]: <captions[1]>\n"
                       "[Reference 3]: <captions[2]>\n"
        }
    ],
    "temperature": 0.3,
    "max_tokens": 512,
    "top_n": 1,
}
```

**API 端点：**
```
POST https://api.minimax.chat/v1/text/chatcompletion_v2?GroupId={api_key}
```

**请求头：**
```python
{
    "Content-Type": "application/json",
    "Authorization": f"Bearer {signature}",   # HMAC-SHA256 签名
    "X-Timestamp": timestamp,                  # Unix 时间戳
}
```

签名生成方式（`_build_request_id`）：
```python
auth = f"{api_key}:{timestamp}"
sig = base64(hmac_sha256(api_secret, auth))
```

#### `paraphrase()` 输出

| 情况 | 返回值 |
|------|--------|
| 正常 | `["一句 paraphrase"]` — 单元素列表 |
| 失败 | `[]` — 空列表 |

**成功响应解析（`_parse_response`）：**
```python
content = choices[0].get("messages", [{}])[0].get("text", "").strip()
lines = content.split("\n")
return [lines[0]] if lines else []   # 取第一行
```

> **注意**：MiniMax 返回格式为 `choices[0].messages[0].text`，与其他厂商不同。

---

### 错误类型汇总

| 错误场景 | 异常类型 | 处理方式 | 用户可见信息 |
|----------|----------|----------|--------------|
| `api_secret` 未设置 | `AssertionError` | 抛出 | `"MiniMax API Secret 未设置"` |
| `api_key` 或 `api_secret` 未设置 | `AssertionError` | 抛出 | `"MiniMax API Key 或 Secret 未设置"` |
| 网络超时 | `urllib.error.URLError` | 捕获 → 返回 `[]` | `print("[MiniMax paraphrase] 请求失败: {e}")` |
| HTTP 4xx/5xx | `urllib.error.HTTPError` | 捕获 → 返回 `[]` | `print("[MiniMax paraphrase] 请求失败: {e}")` |
| JSON 解析失败 | `json.JSONDecodeError` | 捕获 → 返回 `[]` | `print("[MiniMax paraphrase] 请求失败: {e}")` |
| 响应无 choices | — | 返回 `[]` | `print("[MiniMax paraphrase] no choices in response: {data}")` |

---

## OpenAICompatParaphraseModel

### 类定义

```python
@register_model("openai_compat")
class OpenAICompatParaphraseModel(AbstractParaphraseModel):
    def __init__(self, base_url: str = "https://api.openai.com/v1",
                 api_key: str = "", model: str = "gpt-4o-mini",
                 timeout: int = 60):
```

### 完整输入输出

#### `paraphrase()` 输入

**参数：**
- `captions: List[str]` — 1~3 条参考标注

**构建的 Payload：**

```python
payload = {
    "model": "gpt-4o-mini",             # 可配置，默认 "gpt-4o-mini"
    "messages": [
        {
            "role": "system",
            "content": SYSTEM_PROMPT      # 见上文
        },
        {
            "role": "user",
            "content": "Please generate one paraphrase based on the following reference captions:\n\n"
                       "[Reference 1]: <captions[0]>\n"
                       "[Reference 2]: <captions[1]>\n"
                       "[Reference 3]: <captions[2]>\n"
        }
    ],
    "temperature": 0.3,
    "max_tokens": 512,
}
```

**API 端点：**
```
POST {base_url}/chat/completions
```

默认 `base_url = "https://api.openai.com/v1"`，可配置为任意 OpenAI 兼容端点（如 `https://api.minimaxi.com/v1`）。

**请求头：**
```python
{
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",   # 可为空
}
```

#### `paraphrase()` 输出

| 情况 | 返回值 |
|------|--------|
| 正常 | `["一句 paraphrase"]` — 单元素列表 |
| 失败 | `[]` — 空列表 |

**成功响应解析（`_parse_response`）：**
```python
content = choices[0].get("message", {}).get("content", "").strip()
# 去掉思考标签
content = re.sub(r"<think>.*?
</think>

", "", content, flags=re.DOTALL).strip()
lines = content.split("\n")
return [lines[0]] if lines else []   # 取第一行
```

> **注意**：OpenAI 兼容格式为 `choices[0].message.content`，且会去掉 `<think>...
</think>` 思考标签后取第一行。

---

### 错误类型汇总

| 错误场景 | 异常类型 | 处理方式 | 用户可见信息 |
|----------|----------|----------|--------------|
| `base_url` 未设置 | `AssertionError` | 抛出 | `"OpenAI-compatible base_url 未设置"` |
| 网络超时 | `urllib.error.URLError` | 捕获 → 返回 `[]` | `print("[OpenAI paraphrase] 请求失败: {e}")` |
| HTTP 4xx/5xx | `urllib.error.HTTPError` | 捕获 → 返回 `[]` | `print("[OpenAI paraphrase] HTTP {code}: {body}")` |
| JSON 解析失败 | `json.JSONDecodeError` | 捕获 → 返回 `[]` | `print("[OpenAI paraphrase] 请求失败: {e}")` |
| 响应无 choices | — | 返回 `[]` | `print("[OpenAI paraphrase] no choices in response: {data}")` |

---

## 调用数据流

```
ann_lines (全部帧标注)  +  review_flags (审核标志)
       ↓
find_ref(idx) — 向前搜索最多3条非 HALLUCINATION/AI_GENERATED 的有效标注
       ↓
model.paraphrase(caps) — 基于多条参考生成一句 paraphrase
       ↓
返回单句结果（列表）
```

**`find_ref` 逻辑（main_window.py:675）：**

```python
def find_ref(idx: int):
    caps = []
    for candidate in range(idx - 1, -1, -1):   # 向前遍历
        if candidate 超出范围:
            break
        flag = review_flags.get(candidate)
        ftype = flag.get("type") if flag else None
        if ftype in ("HALLUCINATION", "AI_GENERATED"):
            continue                            # 跳过标记帧
        caption = ann_lines[candidate].strip()
        if not caption:
            continue                            # 跳过空caption（不中断）
        caps.append(caption)
        if len(caps) >= 3:
            break
    return list(reversed(caps))                # 倒序转正序
```

---

## 使用示例

```python
from core.paraphrase_model import create_paraphrase_model

# MiniMax（默认）
model = create_paraphrase_model("minimax", api_key="xxx", api_secret="yyy")
result = model.paraphrase(["A dog running in the park", "A cat sitting on a wall"])
# result: ["A dog runs in the park"] 或类似一句改写

# OpenAI 兼容
model = create_paraphrase_model(
    "openai_compat",
    base_url="https://api.minimaxi.com/v1",
    api_key="sk-xxxx",
    model="MiniMax-M2.5-highspeed"
)
result = model.paraphrase(["A dog running in the park"])
# result: ["A dog runs in the park"]
```
