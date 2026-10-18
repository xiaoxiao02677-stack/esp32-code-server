#!/usr/bin/env python3
"""Verify nointent tool passing: import connection module and check branch conditions statically + live log check."""
import subprocess

# 1. static check: the deployed file has our branches
r = subprocess.run(['python', 'code/.workbuddy/ssh_run.py',
    "grep -n 'nointent' /root/xiaozhi-server/main/yuhe-server/core/connection.py | head -8"],
    capture_output=True, text=True, encoding='utf-8', errors='replace', cwd='G:/demo/21_xiaozhi', timeout=60)
print("=== deployed connection.py nointent branches ===")
print(r.stdout)

# 2. live check: restart done; next device connect should log 函数列表 with self_audio_speaker_set_volume
# (device must reconnect - volume tools are registered on mcp handshake)
r = subprocess.run(['python', 'code/.workbuddy/ssh_run.py',
    "tail -50 /root/xiaozhi-server/main/yuhe-server/tmp/server.log | grep -E '函数列表|初始化组件' | tail -5"],
    capture_output=True, text=True, encoding='utf-8', errors='replace', cwd='G:/demo/21_xiaozhi', timeout=60)
print("=== live logs after restart ===")
print(r.stdout if r.stdout.strip() else "(no device connected yet - waiting for real device reconnect)")
