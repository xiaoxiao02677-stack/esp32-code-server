import json, time, urllib.request, ssl, paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"
LOG=f"{BASE}/data/app.log"

def push():
    body=json.dumps({"device_id":"yuhe-44bd8d7b3ae4",
        "payload":{"wake_word":["zao shang hao"],"wake_word_display":["早上好"]},
        "log_tag":"prod-verify-logtest"}).encode()
    req=urllib.request.Request("https://sandyun.top:8003/api/device-config/push", data=body,
        headers={"Content-Type":"application/json","Authorization":"Bearer "+open("../../../.tmp_token","r").read().strip() if False else ""})
    ctx=ssl._create_unverified_context()
    try:
        r=urllib.request.urlopen(req, timeout=15, context=ctx)
        return r.status, r.read().decode()
    except Exception as e:
        return "ERR", str(e)

print("PUSH:", push(), flush=True)
time.sleep(2)

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("grep 已缓存至:", sh(f"grep -c '已缓存至' {LOG}"))
print("grep 推送唤醒词:", sh(f"grep -c '推送唤醒词' {LOG}"))
print("grep 无目标设备:", sh(f"grep -c '无目标设备可推送' {LOG}"))
print("--- 日志最后 6 行 ---")
print(sh(f"tail -6 {LOG}"))
c.close()
