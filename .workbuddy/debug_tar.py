import subprocess
posix = r"G:\demo\21_xiaozhi\console-v2\dist".replace("\\", "/")
# 键：字符串直传会撞上编码/转义问题；改用 stdin 传命令，stderr 也捕获
cmd = f"tar -czf /tmp/v2dbg.tar.gz -C '{posix}' . ; echo EXIT=$? ; ls -la /tmp/v2dbg.tar.gz"
r = subprocess.run(["bash", "-s"], input=cmd.encode(), capture_output=True)
print("rc:", r.returncode)
print("OUT:", r.stdout.decode("utf-8", "replace")[:500])
print("ERR:", r.stderr.decode("utf-8", "replace")[:300])
