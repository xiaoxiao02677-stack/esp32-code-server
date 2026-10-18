#!/usr/bin/env python3
"""生产前端部署：dist-admin → /var/www/console-v2/admin

约束（来自实测）：
1. /admin/ 与 /admincc/ 是同一目录的两个 alias，index.html 里资源写死 /admincc/assets/
2. 资源缺失不会 404，而是被 try_files 回落成 index.html（200 + text/html）
   → 发布漏文件时浏览器只白屏，必须逐个体 md5 校验
3. **只新增不删除旧 assets**：仍持有旧 index.html 的浏览器要能继续加载旧 hash
4. 先 assets 后 index.html（mv 原子替换），避免半截 HTML 被读到
5. 不需要 nginx reload（alias 直读文件系统、无 open_file_cache）

用法：python deploy_web.py --dry-run | --go | --rollback
"""
import sys
import os
import hashlib
import subprocess
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
LOCAL_DIR = r"G:/demo/21_xiaozhi/yh/console-v2/dist-admin"
REMOTE_DIR = "/var/www/console-v2/admin"
TAG = "wakeword-20261017"

ASSETS = [
    ("assets/index-CR0JikiI.js", "9f5d974f3893d8c9733064123e7ccec5", 510157),
    ("assets/index-DnyFrbuD.css", "1325a8b90bd18117fd1c342ceccd0e45", 99958),
]
INDEX = ("index.html", "4fb703fa03ac224938d5115edea770eb", 792)


def md5_local(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, banner_timeout=20, auth_timeout=20,
              look_for_keys=False, allow_agent=False)
    return c


def run(c, cmd, timeout=120):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    return o.channel.recv_exit_status(), out.strip(), err.strip()


def main():
    go = "--go" in sys.argv
    print("=" * 70)
    print("前端部署", "（正式执行）" if go else "（DRY-RUN 预检）")
    print("=" * 70)

    print("\n[1] 本地产物校验")
    for rel, want, size in [INDEX] + ASSETS:
        p = os.path.join(LOCAL_DIR, rel)
        if not os.path.exists(p):
            print(f"  [FAIL] 缺失 {p}")
            return 1
        m, s = md5_local(p), os.path.getsize(p)
        ok = (m == want and s == size)
        print(f"  {'OK  ' if ok else 'FAIL'} {rel} md5={m} size={s}")
        if not ok:
            return 1

    idx = open(os.path.join(LOCAL_DIR, "index.html"), encoding="utf-8").read()
    for name, _, _ in ASSETS:
        fn = name.split("/")[-1]
        if fn not in idx:
            print(f"  [FAIL] index.html 未引用 {fn}")
            return 1
    print("  index.html 引用的资源名与 assets 实际文件一致 OK")
    print("  资源前缀 =", "/admincc/assets/" if "/admincc/assets/" in idx else "（非 /admincc/，需警惕）")

    c = connect()
    try:
        print("\n[2] 线上现状")
        rc, out, _ = run(c, f"ls -l {REMOTE_DIR}/ {REMOTE_DIR}/assets/ | head -20; "
                            f"md5sum {REMOTE_DIR}/index.html {REMOTE_DIR}/assets/*.js {REMOTE_DIR}/assets/*.css")
        print(out)

        if not go:
            print("\n[DRY-RUN] 未修改。加 --go 执行。")
            return 0

        print("\n[3] 备份当前 admin（线上这版没有现存备份，必须现场做）")
        rc, out, err = run(c, f"cp -a {REMOTE_DIR} /var/www/console-v2/admin.bak-{TAG} && "
                              f"md5sum /var/www/console-v2/admin.bak-{TAG}/index.html && "
                              f"ls /var/www/console-v2/admin.bak-{TAG}/assets/")
        print(f"   rc={rc}\n{out}\n{err}")
        if rc != 0:
            return 1

        print("\n[4] 上传（先 assets，index.html 单独最后放）")
        sftp = c.open_sftp()
        for rel, want, size in ASSETS:
            lp = os.path.join(LOCAL_DIR, rel)
            rp = f"{REMOTE_DIR}/{rel}"
            newp = rp + ".new"
            sftp.put(lp, newp)
            print(f"   {rel} -> {newp} ({sftp.stat(newp).st_size} B)")
        lp = os.path.join(LOCAL_DIR, "index.html")
        sftp.put(lp, f"{REMOTE_DIR}/index.html.new")
        print(f"   index.html -> index.html.new")
        sftp.close()

        print("\n[5] 远端 md5 校验（不通过绝不替换）")
        rc, out, _ = run(c, f"md5sum {REMOTE_DIR}/assets/*.new {REMOTE_DIR}/index.html.new")
        print("   " + out.replace("\n", "\n   "))
        for _, want, _ in ASSETS + [INDEX]:
            if want not in out:
                print(f"  [FAIL] 远端缺 {want}")
                run(c, f"rm -f {REMOTE_DIR}/assets/*.new {REMOTE_DIR}/index.html.new")
                return 1

        print("\n[6] 原子替换（assets 先，index.html 后；不删旧 hash）")
        cmds = [f"mv -f {REMOTE_DIR}/{rel}.new {REMOTE_DIR}/{rel}" for rel, _, _ in ASSETS]
        cmds.append(f"mv -f {REMOTE_DIR}/index.html.new {REMOTE_DIR}/index.html")
        rc, out, err = run(c, " && ".join(cmds) + f" && ls -l {REMOTE_DIR}/assets/ && "
                              f"md5sum {REMOTE_DIR}/index.html")
        print(f"   rc={rc}\n{out}\n{err}")

        print("\n[7] HTTP 双入口实测（8001 = 真实浏览器路径）")
        checks = [
            ("/admincc/", "4fb703fa03ac224938d5115edea770eb"),
            ("/admin/", "4fb703fa03ac224938d5115edea770eb"),
            ("/admincc/assets/index-CR0JikiI.js", "9f5d974f3893d8c9733064123e7ccec5"),
            ("/admin/assets/index-CR0JikiI.js", "9f5d974f3893d8c9733064123e7ccec5"),
            ("/admincc/assets/index-DnyFrbuD.css", "1325a8b90bd18117fd1c342ceccd0e45"),
        ]
        allok = True
        for path, want in checks:
            rc, out, _ = run(c, "curl -sk --resolve sandyun.top:8001:127.0.0.1 "
                                f"https://sandyun.top:8001{path} | md5sum")
            got = out.split()[0] if out else ""
            ok = got == want
            allok = allok and ok
            print(f"   {'OK  ' if ok else 'FAIL'} {path} md5={got}")

        print("\n[8] 旧 hash 仍可访问（保证未强刷的浏览器不白屏）")
        rc, out, _ = run(c, "curl -sk -o /dev/null -w '%{http_code} %{size_download}' --resolve "
                            "sandyun.top:8001:127.0.0.1 https://sandyun.top:8001/admincc/assets/index-C0A8D3rv.js")
        print(f"   旧 js: {out}")

        print("\n" + "=" * 70)
        print("前端部署", "完成" if allok else "有校验失败，请回滚",
              "｜回滚：python deploy_web.py --rollback")
        print("=" * 70)
        return 0 if allok else 1
    finally:
        c.close()


def rollback(c):
    print("[ROLLBACK] 恢复 admin 备份")
    rc, out, err = run(c, f"rm -rf {REMOTE_DIR} && cp -a /var/www/console-v2/admin.bak-{TAG} {REMOTE_DIR} && "
                          f"md5sum {REMOTE_DIR}/index.html && ls {REMOTE_DIR}/assets/")
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
