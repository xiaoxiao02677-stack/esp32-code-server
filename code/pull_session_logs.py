# -*- coding: utf-8 -*-
"""拉取生产日志 16:40-17:00 窗口（COM18 新固件测试会话）——查 TTS 截断实锤。"""
import paramiko

HOST, PORT, USER, PWD = "sandyun.top", 22222, "root", "Ymm6088."
LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"

cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(HOST, port=PORT, username=USER, password=PWD, timeout=30)


def run(title, cmd, tail=60):
    _, out, err = cli.exec_command(cmd)
    text = out.read().decode("utf-8", "replace").strip()
    print(f"===== {title} =====")
    lines = text.splitlines()
    if len(lines) > tail:
        print(f"(共 {len(lines)} 行，显示末 {tail} 行)")
        lines = lines[-tail:]
    print("\n".join(lines) if lines else "(空)")
    print()


# 1. 本设备会话窗口
run("设备会话（SiFuDeDohycaCh / MAC）",
    f"grep -E '261018 16:(4[0-9]|5[0-9])' {LOG} | grep -E 'SiFuDeDohycaCh|44:bd:8d:7b:3a:e4' | head -80", tail=80)

# 2. abort / 打断证据
run("abort/打断/中断",
    f"grep -E '261018 16:(4[0-9]|5[0-9])' {LOG} | grep -iE 'abort|打断|中断|interrupt|停止发送' | head -50")

# 3. TTS 合成与发送
run("TTS 合成与发送",
    f"grep -E '261018 16:(4[0-9]|5[0-9])' {LOG} | grep -iE 'tts|合成|sentence' | head -70")

# 4. 故事文本出现处（LLM 响应全文线索）
run("故事文本（糖水/琳琳/修表/年轻人）",
    f"grep -E '261018 16:' {LOG} | grep -E '糖水|琳琳|阿婆|修表|钟表|年轻人|板凳' | head -40")

# 5. ASR 文本（回声证据）
run("ASR 识别文本",
    f"grep '识别文本' {LOG} | grep -E '261018 16:(4[0-9]|5[0-9])' | head -30")

# 6. 回声拦截
run("回声拦截",
    f"grep '回声拦截' {LOG} | grep -E '261018 16:(4[0-9]|5[0-9])' | head -10")

cli.close()
print("DONE")
