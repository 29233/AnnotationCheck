#!/usr/bin/env python3
"""
属性修正 paraphrase 能力测试脚本

测试 AI 能否在给定目标属性键值对的情况下，对包含属性描述错误的 caption 进行修正。

用法：
    python test_paraphrase_attribute_fix.py

测试用例：
    1. 描述的属性不符合（clothing 颜色错误）
    2. 描述了不存在的属性（不存在 umbrella）
    3. 缺少部分属性（缺少 backpack）
"""

import json
import sys
from pathlib import Path

# ── 添加项目路径 ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from core.paraphrase_model import MiniMaxParaphraseModel, OpenAICompatParaphraseModel
from core.config_manager import ConfigManager


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.json"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_constraint(attr_props: dict) -> str:
    """将属性字典转换为 AI 指令字符串。"""
    if not attr_props:
        return ""
    lines = ["Target properties (use these to correct attribute errors in captions):"]
    for key, val in attr_props.items():
        lines.append(f"- {key}: {val}")
    return "\n".join(lines)


def test_case(model, reference_captions: list, attr_props: dict, case_name: str):
    """对单个测试用例执行 paraphrase 并打印结果。"""
    print(f"\n{'='*70}")
    print(f"测试用例：{case_name}")
    print(f"{'='*70}")
    print(f"参考 caption：{reference_captions}")
    print(f"属性配置：{attr_props}")

    constraint = build_constraint(attr_props)
    results = model.paraphrase(
        reference_captions,
        debug_idx=0,
        neighbor_texts=[],
        diversity_threshold=1.0,   # 关闭多样性检查（任何相似度 < 1.0 都通过）
        max_retries=2,
        extra_constraint=constraint,
    )

    if results:
        print(f">> 修正结果：{results[0]}")
    else:
        print(">> 修正结果：（无返回）")
    return results


def main():
    # 加载配置
    data_root = Path(__file__).parent
    config = ConfigManager()
    cfg = config.get_paraphrase_model_config()
    attr_props = config.get_attribute_properties()

    # 选择模型
    mt = cfg.get("model_type", "minimax")
    print(f"\n使用模型类型：{mt}")

    if mt == "openai_compat":
        model = OpenAICompatParaphraseModel(
            base_url=cfg.get("openai_base_url", ""),
            api_key=cfg.get("openai_api_key", ""),
            model=cfg.get("openai_model", "gpt-4o-mini"),
        )
    else:
        model = MiniMaxParaphraseModel(
            api_key=cfg.get("minimax_api_key", ""),
        )

    # ── 参考 caption（正常帧的标注）────────────────────────────
    ref_captions = [
        "A person walks along a city street with buildings in the background, "
        "carrying a white shopping bag in one hand."
    ]

    # ── 测试一：描述的属性不符合 ───────────────────────────────
    # 假设 caption 说 "dark clothing"，但实际目标是 "white/light top"
    # 这是我们新增的 ATTRIBUTE_ERROR 场景
    case1_props = {
        "top_color": "white",
        "pants_color": "black",
        "clothing": "white top and black pants",
    }
    test_case(
        model, ref_captions, case1_props,
        "1. 属性描述不符合（实际：白色上衣+黑色裤子）"
    )

    # ── 测试二：描述了不存在的属性 ─────────────────────────────
    # 假设 caption 说 "holding an umbrella"，但实际目标没有撑伞
    case2_props = {
        "umbrella": "NOT present — the person does NOT hold an umbrella",
    }
    test_case(
        model, ref_captions, case2_props,
        "2. 描述了不存在的属性（实际：无 umbrella）"
    )

    # ── 测试三：缺少部分属性 ─────────────────────────────────
    # 假设 caption 没有提到 backpack，但实际目标背着包
    case3_props = {
        "backpack": "carrying a black backpack on the back",
    }
    test_case(
        model, ref_captions, case3_props,
        "3. 缺少部分属性（实际：背着黑色背包）"
    )

    # ── 测试四：使用当前配置的属性 ───────────────────────────
    if attr_props:
        print(f"\n{'='*70}")
        print("测试用例：4. 使用当前保存的目标属性配置")
        print(f"{'='*70}")
        print(f"当前属性配置：{attr_props}")
        constraint = build_constraint(attr_props)
        results = model.paraphrase(
            ref_captions,
            debug_idx=0,
            neighbor_texts=[],
            diversity_threshold=1.0,
            max_retries=2,
            extra_constraint=constraint,
        )
        if results:
            print(f">> 修正结果：{results[0]}")
        else:
            print(">> 修正结果：（无返回）")
    else:
        print("\n当前未配置 attribute_properties，跳过测试四。")
        print("可通过 工具 → 目标属性配置... 进行配置。")

    print(f"\n{'='*70}")
    print("测试完成")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
