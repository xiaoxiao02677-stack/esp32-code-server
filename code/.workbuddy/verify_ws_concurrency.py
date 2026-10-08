#!/usr/bin/env python3
"""WS 并发上限实测（LimitNOFILE 提到 65535 之后重新测定）。

分级加压：100 → 200 → 400 → 800，每级建连后保持 3s 再全部关闭，
任一级出现失败即停止。用完必须清理干净，不留僵尸连接。
"""
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

SCRIPT = r'''
import asyncio, time, sys, resource
sys.path.insert(0, "/root/xiaozhi-server/main/xiaozhi-server")
from websockets.asyncio.client import connect

URL = "ws://127.0.0.1:8000/xiaozhi/v1/"
HEADERS = {"device-id": "stress-%d", "client-id": "stress-%d"}


async def one(i, results):
    h = {"device-id": f"stress-{i}", "client-id": f"stress-{i}"}
    try:
        ws = await asyncio.wait_for(connect(URL, additional_headers=h,
                                            open_timeout=15), timeout=20)
        results.append(ws)
        return True
    except Exception as e:
        print(f"   连接 {i} 失败: {type(e).__name__}: {e}")
        return False


async def level(n):
    results = []
    t0 = time.time()
    tasks = [asyncio.create_task(one(i, results)) for i in range(n)]
    outs = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for o in outs if o is True)
    dt = time.time() - t0
    await asyncio.sleep(3)
    # 统计 fd
    try:
        fd = len(__import__("os").listdir("/proc/self/fd"))
    except Exception:
        fd = -1
    for ws in results:
        try:
            await ws.close()
        except Exception:
            pass
    await asyncio.sleep(1)
    print(f"  N={n:4d}  ok={ok:4d}  fail={n-ok:4d}  耗时={dt:.2f}s  客户端fd={fd}")
    return ok, n - ok


async def main():
    print("soft nofile:", resource.getrlimit(resource.RLIMIT_NOFILE))
    for n in (100, 200, 400, 800):
        ok, fail = await level(n)
        if fail > 0:
            print(f"\n→ 在 N={n} 出现失败，停止加压。上一档 N 为可承载值。")
            break
    else:
        print(f"\n→ 800 并发全部成功，未触顶。")

asyncio.run(main())
'''

client = get_client()
try:
    cmd = ("cd /root/xiaozhi-server/main/xiaozhi-server && "
           "cat > /tmp/_stress.py <<'PYEOF'\n" + SCRIPT + "\nPYEOF\n"
           ".venv/bin/python /tmp/_stress.py")
    _, out, err = client.exec_command(cmd, timeout=400)
    print(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace")
    if e.strip():
        print("[stderr]", e[-2000:])
finally:
    client.close()
