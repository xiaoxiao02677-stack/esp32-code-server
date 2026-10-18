#!/usr/bin/env python3
"""部署 topic_generator chat 兜底修复到生产并验证。"""
import paramiko

FILES = [
    (r"G:\demo\21_xiaozhi\yh\yuhe-server\core\services\topic_generator.py",
     "/root/xiaozhi-server/main/yuhe-server/core/services/topic_generator.py"),
]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('sandyun.top', port=22222, username='root', password='Ymm6088.',
          look_for_keys=False, allow_agent=False, timeout=15)

sftp = c.open_sftp()

_, o, _ = c.exec_command(
    "cp /root/xiaozhi-server/main/yuhe-server/core/services/topic_generator.py "
    "/tmp/echo_guard_bak/topic_generator.py && echo BAK_OK", timeout=30)
print("备份:", o.read().decode().strip())

for local, remote in FILES:
    sftp.put(local, remote)
    print("上传:", remote)

_, o, e = c.exec_command(
    "cd /root/xiaozhi-server/main/yuhe-server && "
    ".venv/bin/python -m py_compile core/services/topic_generator.py && echo COMPILE_OK",
    timeout=60)
out = o.read().decode().strip()
print("编译:", out)
if "COMPILE_OK" not in out:
    print("!! 编译失败，回滚")
    c.exec_command("cp /tmp/echo_guard_bak/topic_generator.py "
                   "/root/xiaozhi-server/main/yuhe-server/core/services/topic_generator.py", timeout=30)
    c.close(); raise SystemExit(1)

_, o, _ = c.exec_command("systemctl restart yuhe-server && sleep 4 && systemctl is-active yuhe-server", timeout=60)
print("重启:", o.read().decode().strip())

# 验证：创建一个 memory-only 的推送任务（生产实测路径），应成功而非 failed
K = '2d7b6bde-4de9-49f1-9072-476cec13292e'
import json
body = json.dumps({
    "device_ids": ["44:bd:8d:7b:3a:e4"],
    "content": {"push_type": "random", "topic_sources": ["memory"], "text": "", "audio_url": "", "subtitles": []},
    "schedule": {"type": "immediate"},
    "rate_limit": {"per_device": 3, "window_seconds": 300}
})
# 用 heredoc 避免 shell 引号问题
_, o, _ = c.exec_command(
    f"cat > /tmp/push_test.json << 'EOF'\n{body}\nEOF\n"
    f"sleep 8 && curl -s -X POST -H 'Authorization: Bearer {K}' -H 'Content-Type: application/json' "
    f"-d @/tmp/push_test.json http://127.0.0.1:8003/api/push/schedule", timeout=120)
create_resp = o.read().decode('utf-8', 'replace').strip()
print("创建任务:", create_resp[:300])

# 等执行完再查状态
_, o, _ = c.exec_command("sleep 12", timeout=60)
_, o, _ = c.exec_command(
    f"curl -s -H 'Authorization: Bearer {K}' http://127.0.0.1:8003/api/push/tasks",
    timeout=30)
print("任务列表:", o.read().decode('utf-8', 'replace')[:800])

sftp.close()
c.close()
print("DEPLOY_TOPIC_FIX_DONE")
