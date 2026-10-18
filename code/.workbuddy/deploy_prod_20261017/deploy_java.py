#!/usr/bin/env python3
"""生产 Java 部署：上传 jar → md5 校验 → 原子替换 → systemctl restart → 就绪探活。

关键校验（历史踩过的坑）：
  jar 被 mv 覆盖但 JVM 没真正重启时，unit 时间戳完全正常、md5 也对，
  但跑的是旧 inode。所以必须读 /proc/<pid>/fd 里指向该 jar 的 fd，
  比对它的 inode 与磁盘 inode 是否一致。

用法：python deploy_java.py --dry-run | --go | --rollback
"""
import sys
import os
import time
import hashlib
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
LOCAL_JAR = r"G:/demo/21_xiaozhi/yh/manager-api/target/xiaozhi-esp32-api.jar"
WANT_MD5 = "4efef7161ab3ed69474bdb27ee5b468b"
WANT_SIZE = 85840471
REMOTE_JAR = "/opt/xiaozhi/xiaozhi-esp32-api.jar"
TAG = "wakeword-20261017"
SERVICE = "xiaozhi-manager-api"


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


def run(c, cmd, timeout=180):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    return o.channel.recv_exit_status(), out.strip(), err.strip()


def probe(c):
    """返回 (active, pid, http_code, disk_inode, fd_inode)"""
    rc, out, _ = run(c,
        f"systemctl is-active {SERVICE}; "
        f"systemctl show -p MainPID --value {SERVICE}; "
        f"stat -c %i {REMOTE_JAR}; "
        f"PID=$(systemctl show -p MainPID --value {SERVICE}); "
        f"ls -l /proc/$PID/fd 2>/dev/null | grep -F 'xiaozhi-esp32-api.jar' | head -1 | "
        f"sed 's/.*xiaozhi-esp32-api.jar//' ; "
        f"readlink /proc/$PID/fd/* 2>/dev/null | grep -F 'xiaozhi-esp32-api.jar' | head -1")
    lines = [l.strip() for l in out.split("\n")]
    active = lines[0] if lines else ""
    pid = lines[1] if len(lines) > 1 else ""
    disk_inode = lines[2] if len(lines) > 2 else ""
    # 更可靠：直接找 fd 指向的路径，再 stat 它
    rc2, out2, _ = run(c,
        f"PID=$(systemctl show -p MainPID --value {SERVICE}); "
        f"for f in /proc/$PID/fd/*; do t=$(readlink $f 2>/dev/null); "
        f"case \"$t\" in *xiaozhi-esp32-api.jar*) echo \"$t|$(stat -c %i \"$t\" 2>/dev/null)\";; esac; done | head -1")
    fd_path, fd_inode = "", ""
    if "|" in out2:
        fd_path, fd_inode = out2.split("|", 1)
    rc3, code, _ = run(c, "curl -s -o /dev/null -w '%{http_code}' --max-time 10 "
                          f"http://127.0.0.1:8002/yuhe/ || echo 000")
    return active, pid, code, disk_inode, fd_inode, fd_path


def main():
    go = "--go" in sys.argv
    print("=" * 74)
    print("Java 部署", "（正式执行）" if go else "（DRY-RUN 预检）")
    print("=" * 74)

    if not os.path.exists(LOCAL_JAR):
        print(f"[FAIL] 本地 jar 不存在: {LOCAL_JAR}")
        return 1
    m, s = md5_local(LOCAL_JAR), os.path.getsize(LOCAL_JAR)
    print(f"[1] 本地 jar md5={m} size={s}")
    if m != WANT_MD5 or s != WANT_SIZE:
        print(f"[FAIL] 与预期不符 ({WANT_MD5}/{WANT_SIZE})")
        return 1

    c = connect()
    try:
        print("\n[2] 生产现状")
        rc, out, _ = run(c,
            f"systemctl is-active mysql redis-server | tr '\\n' ' '; echo; "
            f"md5sum {REMOTE_JAR}; stat -c '%i %s' {REMOTE_JAR}; "
            f"systemctl show -p MainPID -p Restart -p RestartSec {SERVICE}")
        print(out)
        active, pid, code, disk_inode, fd_inode, fd_path = probe(c)
        print(f"    active={active} pid={pid} http={code} disk_inode={disk_inode} "
              f"fd_inode={fd_inode} fd_path={fd_path}")
        if "mysql" not in out or "active" not in out:
            print("[WARN] mysql/redis 状态需确认")

        if not go:
            print("\n[DRY-RUN] 预检完成，未修改。加 --go 执行。")
            return 0

        print("\n[3] 备份当前 jar")
        rc, out, err = run(c,
            f"cp -a {REMOTE_JAR} {REMOTE_JAR}.bak-{TAG} && md5sum {REMOTE_JAR}.bak-{TAG}")
        print(f"   rc={rc} {out} {err}")
        if rc != 0:
            return 1

        print("\n[4] 上传（约 85MB，预计 100s）")
        t0 = time.time()
        sftp = c.open_sftp()
        tmp = "/opt/xiaozhi/xiaozhi-esp32-api.jar.new"
        sent = 0
        with open(LOCAL_JAR, "rb") as f, sftp.open(tmp, "wb") as rf:
            rf.set_pipelined(True)
            while True:
                buf = f.read(1 << 20)
                if not buf:
                    break
                rf.write(buf)
                sent += len(buf)
                if sent % (20 << 20) < (1 << 20):
                    print(f"      {sent // (1 << 20)}MB / {WANT_SIZE // (1 << 20)}MB")
        sftp.close()
        print(f"   上传完成 {sent} B，耗时 {time.time() - t0:.1f}s")

        print("\n[5] 远端校验")
        rc, out, _ = run(c, f"md5sum {tmp}; stat -c %s {tmp}; stat -c %i {tmp}")
        print(f"   {out}")
        if WANT_MD5 not in out:
            print("[FAIL] 远端 md5 不符，删除临时文件，不替换")
            run(c, f"rm -f {tmp}")
            return 1

        print("\n[6] 原子替换 + 重启")
        rc, out, err = run(c,
            f"mv -f {tmp} {REMOTE_JAR} && stat -c '%i %s' {REMOTE_JAR} && "
            f"systemctl restart {SERVICE} && echo RESTARTED")
        print(f"   rc={rc} {out} {err}")
        if "RESTARTED" not in out:
            print("[FAIL] 重启失败")
            return 1

        print("\n[7] 就绪探活（最多 100s，基线 25~30s）")
        deadline = time.time() + 100
        ok = False
        last = ""
        while time.time() < deadline:
            time.sleep(5)
            active, pid, code, disk_inode, fd_inode, fd_path = probe(c)
            last = (f"active={active} pid={pid} http={code} "
                    f"disk_inode={disk_inode} fd_inode={fd_inode}")
            print("   " + last)
            if active == "active" and code == "200" and disk_inode and disk_inode == fd_inode:
                ok = True
                break
        if not ok:
            print("[FAIL] 未就绪或 inode 不一致（可能仍在跑旧 jar）")
            rc, out, _ = run(c, f"tail -40 /opt/xiaozhi/manager-api.log")
            print(out)
            return 1
        print(f"   inode 一致 → JVM 确已加载新 jar（{fd_path}）")

        print("\n[8] 启动异常扫描")
        rc, out, _ = run(c,
            "grep -aE 'BeanCreationException|NoClassDefFoundError|ClassNotFoundException|"
            "APPLICATION FAILED TO START|Pinyin.*Exception' /opt/xiaozhi/manager-api.log | tail -8")
        print("   " + (out.replace("\n", "\n   ") if out else "（无异常）"))

        print("\n[9] pinyin4j 实机自检（OpenAPI 是否已注册阈值字段）")
        rc, out, _ = run(c,
            "curl -s --max-time 10 http://127.0.0.1:8002/yuhe/v3/api-docs | "
            "grep -o -iE 'wakeWordThreshold|interruptThreshold' | sort | uniq -c")
        print("   " + (out if out else "（未在 OpenAPI 中匹配到，需人工核对 DTO 字段名）"))

        print("\n" + "=" * 74)
        print("Java 部署完成。回滚：python deploy_java.py --rollback")
        print("=" * 74)
        return 0
    finally:
        c.close()


def rollback(c):
    print("[ROLLBACK] 恢复上一个 jar 并重启")
    rc, out, err = run(c,
        f"cp -a {REMOTE_JAR}.bak-{TAG} {REMOTE_JAR} && md5sum {REMOTE_JAR} && "
        f"systemctl restart {SERVICE} && sleep 35 && systemctl is-active {SERVICE}")
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
