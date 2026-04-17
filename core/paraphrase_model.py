"""
Paraphrase Model — 解耦的 AI paraphrase 接口层
=================================================

结构说明：
    所有 paraphrase 实现均继承自 AbstractParaphraseModel。
    通过 PARAPHRASE_MODELS 注册表选择使用的模型。

切换模型：
    在 ConfigManager 或 config.json 中设置 "paraphrase_model" 为注册名，
    可选值：minimax、openai_compat

示例（切换为 OpenAI兼容接口）：
    config.set("paraphrase_model", "openai_compat")
    config.set("openai_api_key", "sk-xxxxx")
"""

import re
from abc import ABC, abstractmethod
from typing import List


# ════════════════════════════════════════════════════════════════════════
# 注册表
# ════════════════════════════════════════════════════════════════════════

PARAPHRASE_MODELS: dict = {}


def register_model(name: str):
    """注册装饰器：将模型类加入 PARAPHRASE_MODELS 注册表。"""
    def deco(cls):
        PARAPHRASE_MODELS[name] = cls
        return cls
    return deco


def create_paraphrase_model(model_type: str, **kwargs) -> "AbstractParaphraseModel":
    """根据 model_type 创建对应的 paraphrase 模型实例。默认：minimax"""
    cls = PARAPHRASE_MODELS.get(model_type, PARAPHRASE_MODELS.get("minimax"))
    return cls(**kwargs)


# ════════════════════════════════════════════════════════════════════════
# 抽象基类
# ════════════════════════════════════════════════════════════════════════

class AbstractParaphraseModel(ABC):
    """所有 paraphrase 模型必须实现的接口。"""

    SYSTEM_PROMPT = (
        "You are a professional image captioning assistant. "
        "Your task is to generate a single paraphrase based on reference captions "
        "while strictly following these rules:\n"
        "1. Preserve the MAIN SUBJECT of the scene (person, vehicle, animal, object, etc.) "
        "— do NOT change, add, or remove the subject. The subject must remain identical.\n"
        "2. ONLY rephrase the wording to achieve diversity — do not generate any content "
        "that is not already present in any of the reference captions.\n"
        "3. Keep the description factual and grounded in the image — "
        "do NOT add actions, attributes, or details not supported by the references.\n"
        "4. The input contains 1–3 reference captions from the same video sequence. "
        "Integrate their information into ONE coherent paraphrase, keeping the same subject and tense.\n"
        "5. Length constraint is mandatory: the paraphrase MUST NOT exceed 30 words under any circumstance.\n"
        "6. Prefer concise output: target 20 words or fewer whenever possible without losing key meaning."
    )

    @abstractmethod
    def paraphrase(self, captions: List[str]) -> List[str]:
        """
        对输入的 caption 列表进行 paraphrase。

        参数：
            captions: 1~3 帧原文标注（按帧顺序）
        返回：
            paraphrased: 改写后的 caption 列表（与输入顺序一一对应）
            若 API 调用失败或超时应返回空列表 []
        """
        ...


# ════════════════════════════════════════════════════════════════════════
# MiniMax 实现
# ════════════════════════════════════════════════════════════════════════

@register_model("minimax")
class MiniMaxParaphraseModel(AbstractParaphraseModel):
    """
    MiniMax Anthropic API 兼容实现（使用官方 anthropic SDK）。

    初始化参数：
        api_key:  MiniMax API Key
        model:    模型名称，默认 "MiniMax-M2.5-highspeed"
        timeout:  请求超时秒数，默认 60
    """

    def __init__(self, api_key: str = "", model: str = "MiniMax-M2.5-highspeed",
                 timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def paraphrase(self, captions: List[str], debug_idx: int = None) -> List[str]:
        if not captions:
            return []
        assert self.api_key, "MiniMax API Key 未设置"

        import anthropic

        user_content = "Please generate one paraphrase based on the following reference captions:\n\n"
        for i, cap in enumerate(captions, 1):
            user_content += f"[Reference {i}]: {cap}\n"

        try:
            client = anthropic.Anthropic(
                base_url="https://api.minimaxi.com/anthropic",
                api_key=self.api_key,
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=1.0,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_content}
                ],
            )
            # 收集所有 text 类型的 content block（跳过 thinking block）
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
            if not text_parts:
                print(f"[MiniMax paraphrase] 帧 {debug_idx} — 无 text 块: {response.content}")
                return []
            full_text = "\n".join(text_parts).strip()
            return self._parse_response(full_text)
        except Exception as e:
            print(f"[MiniMax paraphrase] 帧 {debug_idx} 异常: {type(e).__name__}: {e}")
            return []

    def _parse_response(self, content: str) -> List[str]:
        """解析返回内容。返回第一行（一句 paraphrase）。"""
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return [lines[0]] if lines else []


# ════════════════════════════════════════════════════════════════════════
# OpenAI 兼容接口实现
# ════════════════════════════════════════════════════════════════════════

@register_model("openai_compat")
class OpenAICompatParaphraseModel(AbstractParaphraseModel):
    """
    兼容旧配置字段（openai_*），但底层统一改为 Anthropic SDK 调用。
    可用于 MiniMax Anthropic 兼容端点。

    初始化参数：
        base_url: API 端点，如 "https://api.openai.com/v1"
                  或 "https://api.minimaxi.com/v1"
        api_key:  API Key（OpenAI 格式）
        model:    模型名称，如 "MiniMax-M2.5-highspeed"
        timeout:  超时秒数，默认 60
    """

    def __init__(self, base_url: str = "https://api.openai.com/v1",
                 api_key: str = "", model: str = "gpt-4o-mini",
                 timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _collect_text_blocks(self, content_blocks) -> str:
        """
        从 Anthropic 返回的 content blocks 中抽取文本块并拼接。
        自动忽略 thinking/tool_use 等非文本块。
        """
        text_parts: List[str] = []
        for block in content_blocks or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                txt = getattr(block, "text", "") or ""
                if txt.strip():
                    text_parts.append(txt.strip())
        return "\n".join(text_parts).strip()

    def paraphrase(self, captions: List[str], debug_idx: int = None) -> List[str]:
        if not captions:
            return []
        assert self.base_url, "Anthropic base_url 未设置"
        assert self.api_key, "Anthropic API Key 未设置"

        import anthropic

        user_content = "Please generate one paraphrase based on the following reference captions:\n\n"
        for i, cap in enumerate(captions, 1):
            user_content += f"[Reference {i}]: {cap}\n"

        try:
            # 如果用户配置了 /v1 之类路径，自动规整到 Anthropic 兼容端点
            base = self.base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            if not base.endswith("/anthropic"):
                base = f"{base}/anthropic"

            client = anthropic.Anthropic(
                base_url=base,
                api_key=self.api_key,
                timeout=self.timeout,
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=1.0,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            content = self._collect_text_blocks(response.content)
            if not content:
                print(f"[Anthropic paraphrase] 帧 {debug_idx} — 无可解析 text 块: {response.content}")
                return []
            return self._parse_response(content)
        except Exception as e:
            print(f"[Anthropic paraphrase] 帧 {debug_idx} 异常: {type(e).__name__}: {e}")
            return []

    def _parse_response(self, content: str) -> List[str]:
        """
        解析 Anthropic 兼容接口返回内容。
        自动去除 <think>...</think> 思考片段，并返回首条有效改写结果。
        """
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return [lines[0]] if lines else []
    