"""
translation_demo.py
==================
阿里云机器翻译 SDK 最小可用测试脚本。

使用前提：
1.  安装依赖：pip install alibabacloud_alimt20181012==1.1.0
2.  准备阿里云 Access Key（AK/SK）：
    https://ram.console.aliyun.com/manage/ak

用法：
    # 方式一：设置环境变量（推荐，避免密钥硬编码）
    set ALIYUN_ACCESS_KEY_ID=你的AK
    set ALIYUN_ACCESS_KEY_SECRET=你的SK
    python translation_demo.py

    # 方式二：直接运行，脚本会提示输入
    python translation_demo.py
"""

import os
import sys


def _get_credentials():
    """从环境变量读取 AK/SK，若未设置则交互式询问。"""
    ak = os.environ.get("ALIYUN_ACCESS_KEY_ID", "").strip()
    sk = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "").strip()
    if ak and sk:
        return ak, sk

    print("=" * 50)
    print("  阿里云机器翻译 — 凭证配置")
    print("=" * 50)
    ak = input("请输入 Access Key ID（回车使用环境变量）: ").strip()
    sk = input("请输入 Access Key Secret（回车使用环境变量）: ").strip()
    if not ak or not sk:
        print("错误：AK/SK 不能为空，请设置环境变量或重新输入。")
        sys.exit(1)
    return ak, sk


def _create_client(ak: str, sk: str):
    """创建阿里云翻译客户端。"""
    from alibabacloud_tea_openapi.utils_models import Config
    from alibabacloud_alimt20181012.client import Client

    config = Config(
        access_key_id=ak,
        access_key_secret=sk,
        region_id="cn-hangzhou",            # 默认区域
        endpoint="mt.cn-hangzhou.aliyuncs.com",  # 翻译服务固定接入点
    )
    return Client(config)


def translate(text: str, source_lang: str = "zh", target_lang: str = "en") -> str:
    """
    调用阿里云翻译接口，将 text 从 source_lang 翻译到 target_lang。

    常见语言代码：
        zh   中文
        en   英文
        ja   日文
        ko   韩文
        fr   法文
        de   德文
        ru   俄文
        ar   阿拉伯文
        es   西班牙文
        pt   葡萄牙文
        th   泰文
        vi   越南文
        id   印尼文
    """
    from alibabacloud_alimt20181012.models import TranslateGeneralRequest

    request = TranslateGeneralRequest(
        source_text=text,
        source_language=source_lang,
        target_language=target_lang,
        format_type="text",    # 或 "html"
        scene="general",        # 或 "memo"（商品标题）/ "public" / "chat"
    )
    response = _create_client(*_get_credentials()).translate_general(request)

    # 响应结构：response.body.data 是 TranslateGeneralResponseBodyData 对象
    # 正确访问方式：body.data.to_map()["Data"]["Translated"]
    body = response.body
    data = getattr(body, "data", None)
    if data is None:
        raise ValueError("翻译结果为空，请检查 AK/SK 是否有效。")

    # TranslateGeneralResponseBodyData 对象，使用 to_map() 转换为字典
    data_map = data.to_map()
    translated = data_map.get("Translated")
    if not translated:
        print(f"[调试] 响应结构: body={body}, data.to_map()={data_map}")
        raise ValueError("翻译结果为空，请检查 AK/SK 是否有效。")

    return translated


# ────────────────────────────────────────────────────────────────
# 交互式演示
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  阿里云机器翻译 SDK 测试")
    print("=" * 50)

    test_texts = [
        # 中文 → 英文
        ("你好世界", "zh", "en", "中文 → 英文"),
        ("一个人穿着白色上衣和深色裤子走在人行道上。", "zh", "en", "中文 → 英文（较长句）"),
        # 英文 → 中文
        ("A person in a white top and dark pants walks on the sidewalk.", "en", "zh", "英文 → 中文"),
        # 德语
        ("Der Mann trägt einen schwarzen Mantel.", "de", "zh", "德语 → 中文"),
        # 日语
        ("白い服と黒いズボンの人が歩いています。", "ja", "zh", "日语 → 中文"),
    ]

    ak, sk = _get_credentials()
    print(f"\n凭证：{ak[:4]}...（已加载）\n")
    print("-" * 50)

    # 演示1：单独翻译测试
    print("\n【演示1】单句翻译测试\n")
    for text, src, tgt, desc in test_texts:
        try:
            result = translate(text, src, tgt)
            print(f"  {desc}")
            print(f"  原文：{text}")
            print(f"  译文：{result}")
            print()
        except Exception as e:
            print(f"  翻译失败 [{desc}]: {e}\n")

    # 演示2：批量翻译（多行文本，一次调用）
    print("-" * 50)
    print("\n【演示2】批量翻译（多行合并）\n")
    batch = "\n".join(t for t, _, _, _ in test_texts[:3])
    try:
        # 多行用 \n 分隔，一次请求完成
        result = translate(batch, "zh", "en")
        print(f"  批量原文（3句合并）：")
        print(f"  {batch}")
        print(f"\n  译文：")
        print(f"  {result}")
    except Exception as e:
        print(f"  批量翻译失败: {e}")

    print()
    print("=" * 50)
    print("  测试完成！")
    print("=" * 50)
