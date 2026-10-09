#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地验证 doubao_v3.py 改后产出的请求包（绕过项目 import 链）。

项目 import 链会拉 loguru/colorama/opuslib/pydub/yaml 并触发远程配置拉取，
这里用最小 stub 顶掉，只验证 _build_payload 的产出。
"""
import json
import sys
import types

MOD = "core.providers.tts.doubao_v3"


class _Lazy(types.ModuleType):
    def __getattr__(self, name):
        m = types.ModuleType(name)
        sys.modules.setdefault(name, m)
        setattr(self, name, m)
        return m


for name in ("loguru", "colorama", "opuslib_next", "pydub", "yaml"):
    sys.modules.setdefault(name, _Lazy(name))

# config.logger stub
pkg = types.ModuleType("config")
pkg.__path__ = []
logger_mod = types.ModuleType("config.logger")
logger_mod.setup_logging = lambda *a, **k: _Lazy("loguru").logger
logger_mod.build_module_string = lambda *a, **k: ""
logger_mod.create_connection_logger = lambda *a, **k: None
sys.modules["config"] = pkg
sys.modules["config.logger"] = logger_mod

# core.utils.util stub
core_pkg = types.ModuleType("core")
core_pkg.__path__ = []
utils_pkg = types.ModuleType("core.utils")
utils_pkg.__path__ = []
util_mod = types.ModuleType("core.utils.util")
util_mod.check_model_key = lambda *a, **k: ""
sys.modules["core"] = core_pkg
sys.modules["core.utils"] = utils_pkg
sys.modules["core.utils.util"] = util_mod

# core.providers.tts.base stub
prov_pkg = types.ModuleType("core.providers")
prov_pkg.__path__ = []
tts_pkg = types.ModuleType("core.providers.tts")
tts_pkg.__path__ = []


class _Base:
    def __init__(self, config, delete_audio_file):
        self._dynamic_instruction = None
        self.tts_timeout = 10

    def set_dynamic_instruction(self, i):
        self._dynamic_instruction = i


base_mod = types.ModuleType("core.providers.tts.base")
base_mod.TTSProviderBase = _Base
sys.modules["core.providers"] = prov_pkg
sys.modules["core.providers.tts"] = tts_pkg
sys.modules["core.providers.tts.base"] = base_mod

sys.path.insert(0, r"G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server")
import importlib

mod = importlib.import_module(MOD)
TTSProvider = mod.TTSProvider

BASE_CFG = {
    "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4",
    "resource_id": "seed-icl-2.0",
    "private_voice": "S_N8pC5xwg2",
    "format": "mp3",
    "sample_rate": 24000,
}


def show(title, cfg, instruction=None):
    p = TTSProvider(cfg, False)
    if instruction:
        p.set_dynamic_instruction(instruction)
    payload = p._build_payload("今天真是个好日子，我们一起出去玩吧！")
    print(f"\n{'='*72}\n{title}\n{'='*72}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


# 1) 用户在对话里传入语气指令（主场景）
p1 = show("场景1：用户传入语气指令 -> additions.context_texts",
          BASE_CFG, "用非常开心、兴奋、雀跃的语气说话")

# 2) 无指令（基线）
p2 = show("场景2：无语气指令（基线，只带 explicit_language）", BASE_CFG)

# 3) 固定音色指令 voice_instruction
p3 = show("场景3：音色固定指令 voice_instruction",
          dict(BASE_CFG, voice_instruction="用撒娇可爱的语气说话"))

# 4) 后付费复刻
p4 = show("场景4：后付费复刻 custom_speaker_id",
          dict(BASE_CFG, speaker_type="postpaid",
               custom_speaker_id="custom_zh_myvoice01"),
          "用平静的语气说话")

print("\n" + "=" * 72)
print("校验")
print("=" * 72)
ok = True


def chk(cond, msg):
    global ok
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        ok = False


chk(p1["req_params"]["additions"].count("context_texts") == 1
    and json.loads(p1["req_params"]["additions"])["context_texts"]
    == ["用非常开心、兴奋、雀跃的语气说话"],
    "场景1 语气指令进 context_texts")
chk("namespace" in p1 and p1["namespace"] == "BidirectionalTTS",
    "顶层 namespace = BidirectionalTTS")
chk(p1["user"]["uid"] == "xiaozhi-esp32-server", "顶层 user.uid")
chk("model" not in p1["req_params"], "默认不发送 model（对齐官方脚本）")
chk("enable_emotion" not in p1["req_params"]["audio_params"]
    and "emotion_scale" not in p1["req_params"]["audio_params"],
    "默认不发送 enable_emotion / emotion_scale（官方脚本无此字段）")
chk(p1["req_params"]["audio_params"].get("emotion") == "happy",
    "自动推断 emotion=happy 且只发 emotion 单字段")
chk("context_texts" not in p2["req_params"]["additions"],
    "场景2 无指令时不带 context_texts")
chk(json.loads(p3["req_params"]["additions"])["context_texts"]
    == ["用撒娇可爱的语气说话"], "场景3 固定指令进 context_texts")
chk(p4["req_params"]["speaker"] == "custom_speaker_id"
    and p4["req_params"]["custom_speaker_id"] == "custom_zh_myvoice01",
    "场景4 后付费 speaker 占位 + custom_speaker_id")
chk(list(p1.keys()) == ["user", "req_params", "namespace"]
    or set(p1.keys()) == {"user", "req_params", "namespace"},
    f"顶层字段集 = {list(p1.keys())}")

print("\n结论：", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
