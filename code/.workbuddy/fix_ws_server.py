#!/usr/bin/env python3
"""服务器修复脚本：executor 竞态 bug + 超时配置（在服务器上执行）。"""
import re

# ---- 修 1: connection.py executor NoneType 竞态 ----
path = "/root/xiaozhi-server/main/yuhe-server/core/connection.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

old = "            self.executor.submit(self._initialize_components)"
new = (
    "            executor = self.executor  # snapshot: close() sets it None concurrently\n"
    "            if executor is not None:\n"
    "                executor.submit(self._initialize_components)"
)
assert src.count(old) == 1, f"anchor count={src.count(old)}"
with open(path, "w", encoding="utf-8") as f:
    f.write(src.replace(old, new))
print("[1/2] connection.py executor race patched")

# ---- 修 2: 空闲断连 120s -> 3600s（圆屏桌宠常驻在线）----
cfg = "/root/xiaozhi-server/main/yuhe-server/config.yaml"
with open(cfg, encoding="utf-8") as f:
    c = f.read()
c2 = re.sub(r"close_connection_no_voice_time: \d+", "close_connection_no_voice_time: 3600", c)
assert c2 != c, "config pattern not found"
with open(cfg, "w", encoding="utf-8") as f:
    f.write(c2)
print("[2/2] config.yaml close_connection_no_voice_time -> 3600")
