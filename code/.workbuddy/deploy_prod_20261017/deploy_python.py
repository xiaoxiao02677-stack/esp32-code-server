#!/usr/bin/env python3
"""生产 Python 部署：三文件同批替换 + systemctl restart + 就绪判定 + 失败自动回滚。

为什么必须同批：
  http_server.py 注册的路由指向 wake_word_handler.handle_push_device_config，
  handler 再把 display_words 传给 wake_word_service.push_wake_words。
  只换其中一个 → AttributeError / TypeError → systemd Restart=always 每 5s 崩溃重启
  （等价于历史上测试环境那次自重启循环）。

用法：
  python deploy_python.py --dry-run     # 只预检，不动线上
  python deploy_python.py --go          # 真正执行
"""
import sys
import os
import time
import hashlib
import subprocess
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
REMOTE_ROOT = "/root/xiaozhi-server/main/yuhe-server"
STAGING = "/root/staging/py-20261017"
TAG = "prod-20261017"

# 本地 → 远端相对路径；顺序即替换顺序
FILES = [
    (r"G:/demo/21_xiaozhi/yh/yuhe-server/core/services/wake_word_service.py",
     "core/services/wake_word_service.py", "38c7fe7734618af416c4f35818663b42", 24745),
    (r"G:/demo/21_xiaozhi/yh/yuhe-server/core/api/wake_word_handler.py",
     "core/api/wake_word_handler.py", "9588a97a9210c3db1ff9fffb0328bcc2", 7649),
    (r"G:/demo/21_xiaozhi/yh/yuhe-server/core/http_server.py",
     "core/http_server.py", "1a8f01c8399d67bc6db62da1707fa25e", 26890),
]


def md5_local(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, banner_timeout=20, auth_timeout=20,
              look_for_keys=False, allow_agent=False)
    return c


def run(c, cmd, timeout=300):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    return o.channel.recv_exit_status(), out.strip(), err.strip()


def step(n, msg):
    print(f"\n[{n}] {msg}")


def main():
    go = "--go" in sys.argv
    dry = not go
    print("=" * 70)
    print("Python 部署", "（DRY-RUN 预检，不改线上）" if dry else "（正式执行）")
    print("=" * 70)

    step(1, "本地文件校验")
    for local, rel, want_md5, want_size in FILES:
        if not os.path.exists(local):
            print(f"  [FAIL] 缺失 {local}")
            return 1
        m, s = md5_local(local), os.path.getsize(local)
        ok = (m == want_md5 and s == want_size)
        print(f"  {'OK  ' if ok else 'FAIL'} {rel} md5={m} size={s} (expect {want_md5}/{want_size})")
        if not ok:
            return 1

    c = connect()
    try:
        step(2, "生产现状与备份")
        rc, out, _ = run(c, "systemctl is-active yuhe-server; "
                            "systemctl show -p MainPID --value yuhe-server; "
                            f"cd {REMOTE_ROOT} && md5sum " +
                            " ".join(rel for _, rel, _, _ in FILES))
        print(out or "(no output)")

        if dry:
            print("\n[DRY-RUN] 预检通过，未做任何修改。加 --go 执行。")
            return 0

        # 备份（保留原文件时间戳），命名带 TAG 便于回滚
        rc, out, err = run(c,
            f"cd {REMOTE_ROOT} && mkdir -p {STAGING}/bak && "
            + " && ".join(
                f"cp -a {rel} {STAGING}/bak/{rel.replace('/', '__')}.bak-{TAG}"
                for _, rel, _, _ in FILES)
            + f" && ls -l {STAGING}/bak")
        print(f"  备份: rc={rc}\n{out}\n{err}")
        if rc != 0:
            print("[FAIL] 备份失败，终止")
            return 1

        step(3, "上传到 staging 并校验 md5")
        sftp = c.open_sftp()
        for local, rel, want_md5, _ in FILES:
            tmp = f"{STAGING}/{rel.replace('/', '__')}"
            sftp.put(local, tmp)
            st = sftp.stat(tmp)
            print(f"  上传 {rel} -> {tmp} ({st.st_size} B)")
        sftp.close()
        rc, out, _ = run(c, f"cd {STAGING} && md5sum *.py")
        print(out)
        for _, rel, want_md5, _ in FILES:
            if want_md5 not in out:
                print(f"[FAIL] 远端 md5 不含 {want_md5}，终止")
                return 1

        step(4, "同批替换三文件")
        cmds = []
        for _, rel, _, _ in FILES:
            src = f"{STAGING}/{rel.replace('/', '__')}"
            cmds.append(f"install -m 644 {src} {REMOTE_ROOT}/{rel}")
        rc, out, err = run(c, " && ".join(cmds) + f" && cd {REMOTE_ROOT} && md5sum " +
                              " ".join(rel for _, rel, _, _ in FILES))
        print(f"rc={rc}\n{out}\n{err}")
        if rc != 0:
            print("[FAIL] 替换失败，走回滚")
            rollback(c)
            return 1

        step(5, "语法自检（替换后、重启前）")
        rc, out, err = run(c, f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile "
                              "core/services/wake_word_service.py core/api/wake_word_handler.py "
                              "core/http_server.py && echo COMPILE_OK")
        print(f"rc={rc}\n{out}\n{err}")
        if "COMPILE_OK" not in out:
            print("[FAIL] 语法检查失败，回滚")
            rollback(c)
            return 1

        step(6, "重启服务")
        rc, out, err = run(c, "systemctl restart yuhe-server && echo RESTARTED")
        print(f"rc={rc} {out} {err}")

        step(7, "就绪判定（最多 60s）")
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            time.sleep(4)
            rc, out, _ = run(c, "systemctl is-active yuhe-server; "
                                "ss -lntp 2>/dev/null | grep -cE ':8000|:8003'; "
                                "pgrep -fc 'app.py'")
            lines = out.split("\n")
            active = lines[0].strip() if lines else ""
            ports = lines[1].strip() if len(lines) > 1 else "0"
            procs = lines[2].strip() if len(lines) > 2 else "0"
            print(f"  active={active} listening={ports} procs={procs}")
            if active == "active" and ports == "2" and procs == "1":
                ready = True
                break
        if not ready:
            print("[FAIL] 未在 60s 内就绪，检查日志")
            rc, out, _ = run(c, f"tail -40 {REMOTE_ROOT}/data/app.log")
            print(out)
            rollback(c)
            return 1

        step(8, "日志扫描（ERROR/Traceback/ModuleNotFound）")
        rc, out, _ = run(c, f"tail -n 200 {REMOTE_ROOT}/data/app.log | "
                            "grep -nE 'Traceback|ModuleNotFoundError|Address already in use|ERROR' | tail -20")
        print(out if out else "  （无匹配，干净）")
        if out and ("Traceback" in out or "ModuleNotFoundError" in out):
            print("[WARN] 日志有异常，需人工判断（未自动回滚）")

        print("\n" + "=" * 70)
        print("Python 部署完成。回滚命令：")
        print(f"  python deploy_python.py --rollback   （或手工 cp {STAGING}/bak/* 回原路径）")
        print("=" * 70)
        return 0
    finally:
        c.close()


def rollback(c):
    print("\n[ROLLBACK] 从备份恢复三文件并重启")
    cmds = []
    for _, rel, _, _ in FILES:
        bak = f"{STAGING}/bak/{rel.replace('/', '__')}.bak-{TAG}"
        cmds.append(f"mkdir -p $(dirname {REMOTE_ROOT}/{rel}) && cp -a {bak} {REMOTE_ROOT}/{rel}")
    rc, out, err = run(c, " && ".join(cmds) + " && systemctl restart yuhe-server && sleep 8 "
                          "&& systemctl is-active yuhe-server")
    print(f"rc={rc}\n{out}\n{err}")


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        cc = connect()
        try:
            rollback(cc)
        finally:
            cc.close()
        sys.exit(0)
    sys.exit(main())
