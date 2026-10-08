import subprocess
# check: recent sessions - did LLM get the volume tool? search llm request logs / tts logs around 22:30-23:10
r = subprocess.run(['python', 'code/.workbuddy/ssh_run.py',
    "grep -n 'tools\\\\\\\"' /root/xiaozhi-server/main/xiaozhi-server/tmp/server.log | grep -v '收到mcp消息' | tail -3; "
    "grep -n 'SIQwDeDohonoCh' /root/xiaozhi-server/main/xiaozhi-server/tmp/server.log | grep -iE 'llm|chat' | tail -5"],
    capture_output=True, text=True, encoding='utf-8', errors='replace', cwd='G:/demo/21_xiaozhi', timeout=120)
print(r.stdout[-3000:])
