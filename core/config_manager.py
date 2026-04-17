import json
from pathlib import Path

_DEFAULT = {
    "last_data_root": "",
    "last_sequence": "",
    "layout_mode": "A",          # A = visible main, B = infrared main
    "splitter_ratio": [70, 30],  # image splitter proportions
    "auto_save_enabled": True,
    "auto_save_interval": 180,   # seconds
    "aliyun_ak": "",
    "aliyun_sk": "",
    "sdk_configured": False,
    # ── paraphrase ──────────────────────────────────────────────
    "paraphrase_model": "minimax",   # 模型类型：minimax / openai_compat
    "minimax_api_key": "",
    "minimax_api_secret": "",
    "openai_base_url": "",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
}

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class ConfigManager:
    def __init__(self):
        self._data = dict(_DEFAULT)
        self._load()

    def _load(self):
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def set_aliyun_credentials(self, ak: str, sk: str):
        self._data["aliyun_ak"] = ak
        self._data["aliyun_sk"] = sk
        self._data["sdk_configured"] = True
        self.save()

    def get_aliyun_credentials(self):
        return (self._data.get("aliyun_ak", ""),
                self._data.get("aliyun_sk", ""))

    def get_paraphrase_model_config(self) -> dict:
        """返回当前配置的 paraphrase 模型参数字典。"""
        return {
            "model_type": self._data.get("paraphrase_model", "minimax"),
            "minimax_api_key": self._data.get("minimax_api_key", ""),
            "minimax_api_secret": self._data.get("minimax_api_secret", ""),
            "openai_base_url": self._data.get("openai_base_url", ""),
            "openai_api_key": self._data.get("openai_api_key", ""),
            "openai_model": self._data.get("openai_model", "gpt-4o-mini"),
        }
