#!/usr/bin/env python3
"""生产发布用：SFTP 上传 + 远端 md5 校验 + 原子替换。

用法：
  python push_verify.py LOCAL REMOTE                 # 上传到 REMOTE.tmp，校验 md5 后原子 mv 到 REMOTE
  python push_verify.py LOCAL REMOTE --no-replace    # 只上传到 REMOTE.tmp 并校验，不替换
  python push_verify.py --md5 REMOTE                 # 只算远端文件 md5

为什么不用 /tmp：本机验证过 SFTP 写 /tmp 会返回 ENOENT，统一走 /root/staging。
失败即非零退出，且不会留下半截文件覆盖目标（先 .tmp 再 mv）。
"""
import sys
import os
import hashlib
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."


def _fix_remote(p):
    """Git Bash(MSYS) 会把以 / 开头的命令行参数改写成
    D:/INSTALL/workbuddy/resources/vendor/PortableGit/root/...
    导致 SFTP 端拿到一个不存在的路径并返回 ENOENT。
    这里把被改写的前缀剥掉，恢复成真正的远端绝对路径。
    （调用方也可以加 MSYS_NO_PATHCONV=1 从源头避免）"""
    if not p or p.startswith("/"):
        return p
    if "PortableGit" in p or "/Git/" in p or "workbuddy" in p:
        for marker in ("/root/", "/var/", "/opt/", "/etc/", "/usr/", "/home/", "/tmp/"):
            i = p.find(marker)
            if i > 0:
                fixed = p[i:]
                print(f"      [path-fix] {p} -> {fixed}")
                return fixed
    return p


def md5_local(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(retries=4, delay=3.0):
    """并发 SSH 会触发 sshd 的 MaxStartups 软限制（表现为 sftp 建连后立刻 ENOENT），
    因此这里做带退避的重试，而不是把瞬时故障当成路径不存在。"""
    import time
    last = None
    for i in range(retries):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                      timeout=20, banner_timeout=20, auth_timeout=20,
                      look_for_keys=False, allow_agent=False)
            return c
        except Exception as e:
            last = e
            print(f"      [retry {i + 1}/{retries}] 连接失败: {type(e).__name__}: {e}")
            time.sleep(delay * (i + 1))
    raise last


def run(c, cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return 2

    if args[0] == "--md5":
        c = connect()
        try:
            rc, out, err = run(c, f"md5sum {args[1]}")
            print(out or err)
            return 0 if rc == 0 else 1
        finally:
            c.close()

    local, remote = args[0], _fix_remote(args[1])
    replace = "--no-replace" not in args
    if not os.path.exists(local):
        print(f"[FAIL] 本地文件不存在: {local}")
        return 2

    lmd5 = md5_local(local)
    lsize = os.path.getsize(local)
    tmp = remote + ".tmp"
    print(f"[1/4] 本地 {local}  size={lsize} md5={lmd5}")

    c = connect()
    try:
        # 并发 SSH 会让 sftp 的 CMD_OPEN 偶发返回伪 ENOENT，这里对整段上传做重试
        import time
        ok = False
        for attempt in range(1, 4):
            try:
                sftp = c.open_sftp()
                chunk = 1024 * 1024
                sent = 0
                last_pct = -10
                with open(local, "rb") as f, sftp.open(tmp, "wb") as rf:
                    rf.set_pipelined(True)
                    while True:
                        buf = f.read(chunk)
                        if not buf:
                            break
                        rf.write(buf)
                        sent += len(buf)
                        pct = int(sent * 100 / lsize)
                        if pct >= last_pct + 20:
                            print(f"      上传 {pct}% ({sent}/{lsize})")
                            last_pct = pct
                sftp.close()
                ok = True
                break
            except Exception as e:
                print(f"      [upload retry {attempt}/3] {type(e).__name__}: {e}")
                time.sleep(2 * attempt)
        if not ok:
            print("[FAIL] 上传重试耗尽")
            return 1
        print(f"[2/4] 上传完成 -> {tmp}")

        rc, out, err = run(c, f"md5sum {tmp} && stat -c '%s' {tmp}")
        print(f"[3/4] 远端校验: {out or err}")
        rmd5 = out.split()[0] if out else ""
        rsize = out.split("\n")[1].strip() if out and "\n" in out else ""
        if rmd5 != lmd5 or str(lsize) != rsize:
            print(f"[FAIL] 校验不一致 local={lmd5}/{lsize} remote={rmd5}/{rsize}")
            run(c, f"rm -f {tmp}")
            return 1
        print("[3/4] md5 与字节数一致 OK")

        if replace:
            rc, out, err = run(c, f"mv -f {tmp} {remote} && md5sum {remote} && stat -c '%s' {remote}")
            print(f"[4/4] 原子替换: {out or err}")
            if rc != 0 or lmd5 not in out:
                print("[FAIL] 替换后校验失败")
                return 1
        else:
            print(f"[4/4] 保留为 {tmp}（未替换）")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
