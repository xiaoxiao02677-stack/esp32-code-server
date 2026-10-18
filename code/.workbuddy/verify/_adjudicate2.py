import paramiko

BASE = "/root/xiaozhi-server/main/yuhe-server"
LOG = BASE + "/data/app.log"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.",
          timeout=25, look_for_keys=False, allow_agent=False)


def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8", "replace").strip()


print("=== A) 21:28:00~21:29:20 关键事件 ===")
pat = "conn - Headers|异步获取|已下发云端设备配置|收到listen|播放唤醒词回复|识别文本|大模型收到用户消息|客户端断开"
print(sh("sed -n '3020,3130p' " + LOG + " | grep -nE '" + pat + "' | cut -c1-180"))

print("\n=== B) 全部 detect 行（尾部 6 条）===")
print(sh("grep -n 'state...detect' " + LOG + " | tail -6 | cut -c1-160"))

print("\n=== C) 全部 播放唤醒词回复 行 ===")
print(sh("grep -n '播放唤醒词回复' " + LOG + " | tail -6 | cut -c1-160"))

print("\n=== D) 3088~3112 原文 ===")
print(sh("sed -n '3088,3112p' " + LOG + " | cut -c1-170"))
c.close()
