# -*- coding: utf-8 -*-
"""用真实 TTSProvider 类跑线上合成，校验新 payload 与音频产出。"""
import sys, os, types as _t

ROOT = r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server"
sys.path.insert(0, ROOT)


class _Any:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return _Any()
    def __call__(self, *a, **k): return _Any()


class _LazyMod(_t.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Any()


# 1) loguru 依赖 colorama（本地缺）
_cm = _LazyMod("colorama")
_cm.init = lambda *a, **k: None
sys.modules["colorama"] = _cm
sys.modules["colorama.win32"] = _LazyMod("colorama.win32")

# 2) opus 编解码（本地缺原生库）
sys.modules["opuslib_next"] = _LazyMod("opuslib_next")
sys.modules["opuslib_next.constants"] = _LazyMod("opuslib_next.constants")
sys.modules["opuslib_next.classes"] = _LazyMod("opuslib_next.classes")

# 3) pydub（本项目 TTS 后处理用，这里不需要）
sys.modules["pydub"] = _LazyMod("pydub")

import asyncio  # noqa: E402
from core.providers.tts.doubao_v3 import TTSProvider  # noqa: E402

CFG = {
    "type": "doubao_v3", "format": "mp3",
    "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4",
    "api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
    "speaker": "S_N8pC5xwg2", "resource_id": "seed-icl-2.0",
    "sample_rate": "24000",
}
OUT_DIR = r"G:\demo\21_xiaozhi\code\.workbuddy"


def run(tag, instruction=None, **over):
    cfg = dict(CFG); cfg.update(over)
    p = TTSProvider(cfg, False)
    if instruction:
        p.set_dynamic_instruction(instruction)
    pl = p._build_payload("今天真是个好日子，我太开心啦！")
    ap = pl["req_params"]["audio_params"]
    print(f"\n--- {tag} ---")
    print("namespace :", pl.get("namespace"))
    print("speaker   :", pl["req_params"].get("speaker"))
    print("emotion   :", ap.get("emotion"), "scale:", ap.get("emotion_scale"),
          "enable:", ap.get("enable_emotion"))
    print("additions :", pl["req_params"].get("additions"))
    print("model     :", pl["req_params"].get("model"))
    out = os.path.join(OUT_DIR, f"v3_{tag}.mp3")
    asyncio.run(p.text_to_speak("今天真是个好日子，我太开心啦！", out))
    print("音频字节  :", os.path.getsize(out))


run("01_无指令")
run("02_开心指令", "用非常开心、兴奋、雀跃的语气说话")
run("03_生气指令", "用很生气愤怒的语气说话")
run("04_难过指令", "用难过伤心的语气说话")
run("05_中性指令", "用平静自然的语气说话")
run("06_越界scale99", "用开心的语气说话", emotion_scale=99)
run("07_固定emotion", None, emotion="angry")
