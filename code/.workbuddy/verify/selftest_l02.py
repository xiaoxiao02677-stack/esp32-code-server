"""L-02 三项回归（本地，不连服务器）。

做法：先用一个 Fake Remote 把 check_logs 真正生成的远端命令截下来，
从中抽出**实际会执行的 awk 程序**与 ERRPAT/NOISE 常量，再拿合成日志在本地跑，
最后把结果喂回 check_logs 验证判定层。避免"测了一份抄写版 awk"。
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_prod as cp  # noqa: E402

START = "261017 21:02:48"   # 21:02:53 前拨 5s
# Windows 上 Python 的 subprocess 不认 MSYS 的 /usr/bin/bash，必须给真实 exe 路径
BASH = r"D:\INSTALL\workbuddy\resources\vendor\PortableGit\usr\bin\bash.exe"


class Fake:
    def __init__(self, out=""):
        self.out = out
        self.cmd = ""

    def sh(self, cmd, timeout=90):
        self.cmd = cmd
        return 0, self.out


# ---------------------------------------------------------------- 抽取真实 awk
fake = Fake()
cp.check_logs(fake, cp.Report(), "/root/x", False)
CMD = fake.cmd

ERRPAT = re.search(r"^ERRPAT='([^']*)'", CMD, re.M).group(1)
NOISE = re.search(r"^NOISE='([^']*)'", CMD, re.M).group(1)
progs = re.findall(r"""awk -v s="\$PSTART" '\n(.*?)\n'""", CMD, re.S)
assert len(progs) == 2, f"应抽出两段 awk（起点/窗口外），实际 {len(progs)}"
PA = next(p for p in progs if "cur >= s" in p)
PB = next(p for p in progs if "cur < s" in p)
print("=== 抽到的切片 awk（窗口内）===\n" + PA)
print("=== 抽到的切片 awk（窗口外）===\n" + PB)
print(f"=== ERRPAT={ERRPAT}\n=== NOISE={NOISE}")

(HERE / "_pa.awk").write_text(PA + "\n", encoding="utf-8", newline="\n")
(HERE / "_pb.awk").write_text(PB + "\n", encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- 合成日志
def pre(ts, msg):
    return f"{ts}[0.9.7][core.heartbeat]-INFO-{msg}"


def build(with_crash):
    L = []
    for i in range(530):                      # 1..530
        L.append(pre("261017 20:59:58", f"history {i}"))
    L.append("Traceback (most recent call last):")          # 531 ← 窗口外历史异常
    L.append('  File "/root/old.py", line 1, in <module>')
    for i in range(368):                      # 532..900
        L.append(pre("261017 20:59:58", f"history2 {i}"))
    for i in range(1599):                     # 901..2499
        L.append(pre("261017 21:00:30", f"pre-start {i}"))
    L.append("ERROR:发布前就存在的旧错误")                    # 2500 ← 窗口内但启动前
    for i in range(399):                      # 2501..2899
        L.append(pre("261017 21:01:00", f"pre-start2 {i}"))
    L.append(pre("261017 21:02:53", "本轮启动完成"))          # 2900
    L.append(pre("261017 21:03:15", "设备上线 [yuhe-44bd8d7b3ae4]"))
    L.append("WARNING:core.api.wake_word_handler:鉴权失败（token为空或服务端未配置auth_key）")
    L.append(pre("261017 21:04:05", "心跳 [yuhe-44bd8d7b3ae4]"))
    if with_crash:                            # 无前缀异常紧跟窗口内业务行
        L.append(pre("261017 21:05:00", "心跳 [yuhe-44bd8d7b3ae4]"))
        L.append("Traceback (most recent call last):")
        L.append('  File "/root/core/x.py", line 9, in <module>')
        L.append("ModuleNotFoundError: No module named 'core.x'")
    return "\n".join(L) + "\n"


def run_fixture(name, body):
    log = HERE / f"_f_{name}.log"
    log.write_text(body, encoding="utf-8", newline="\n")
    sh = HERE / "_run.sh"
    sh.write_text(r"""
LOG="$1"; S="$2"
AFTER=/tmp/_r_after.$$; BEFORE=/tmp/_r_before.$$
tail -n 2000 "$LOG" | awk -v s="$S" -f _pa.awk > $AFTER
tail -n 2000 "$LOG" | awk -v s="$S" -f _pb.awk | grep -vE "$NOISE" > $BEFORE
echo "AFTER_LINES=$(wc -l < $AFTER | tr -d ' ')"
echo "PERR=$(grep -cE "$ERRPAT" $AFTER)"
echo "PNOISE=$(grep -cE "$NOISE" $AFTER)"
echo "OLDERR=$(tail -n 2000 "$LOG" | awk -v s="$S" '{ if (substr($0,1,15) >= s) print }' | grep -cE "$ERRPAT")"
TOT=$(wc -l < "$LOG" | tr -d ' ')
BASE=$(( TOT > 2000 ? TOT - 2000 : 0 ))
echo "PTOT=$TOT"
echo "PBASE=$BASE"
echo "PTOTERR=$(grep -vE "$NOISE" "$LOG" | grep -cE "$ERRPAT")"
echo "PHIST_LINE=$(head -n $BASE "$LOG" | grep -nE "$ERRPAT" | head -1 | cut -d: -f1)"
echo "PHIST_IDX=$(grep -nE "$ERRPAT" $BEFORE | head -1 | cut -d: -f1)"
rm -f $AFTER $BEFORE
""", encoding="utf-8", newline="\n")
    env_cmd = [BASH, str(sh).replace("\\", "/"), str(log).replace("\\", "/"), START]
    # 变量在远端 shell 里是预先 echo 的常量，这里等价注入
    sh.write_text(sh.read_text(encoding="utf-8").replace(
        'LOG="$1"; S="$2"',
        f"LOG=\"$1\"; S=\"$2\"\nERRPAT='{ERRPAT}'\nNOISE='{NOISE}'"),
        encoding="utf-8", newline="\n")
    r = subprocess.run(env_cmd, capture_output=True, cwd=str(HERE))
    out = r.stdout.decode("utf-8", "replace")
    kv = dict(re.findall(r"^(\w+)=(.*)$", out, re.M))
    log.unlink()
    return kv


print("\n### ② 窗口外历史异常（改之前会假 FAIL）")
h = run_fixture("hist", build(False))
print(h)
assert h["PERR"] == "0", f"窗口内应 0 条异常：{h}"
assert h["PNOISE"] == "1", f"预期噪声应 1 条：{h}"
assert h["OLDERR"] == "1", f"旧写法应误把窗口外 ERROR 算进来（假 FAIL 复现）：{h}"
assert h["PHIST_LINE"] == "531", f"历史异常首条行号应 531：{h}"
assert h["PTOTERR"] == "2", f"全文件异常应 2 条：{h}"

print("\n### ①③a 窗口内无前缀 Traceback（崩溃 → 必须计入）")
w = run_fixture("win", build(True))
print(w)
assert w["PERR"] == "2", f"Traceback + ModuleNotFoundError 应计入 2 行（栈帧不匹配 ERRPAT）：{w}"
assert w["OLDERR"] == "3", f"旧写法此时为 3（多算了窗口外那条 ERROR）：{w}"

# ---------------------------------------------------------------- 判定层
TPL = """@@JSTART=Sat 2026-10-17 21:04:19 CST
@@JERR=0
@@JLOG_BEGIN
Oct 17 21:04:44 Tomcat started on port 8002
@@JLOG_END
@@PSTART=261017 21:02:48
@@PAFTER_LINES={after}
@@PBASE={base}
@@PTOTERR={toterr}
@@PHIST_LINE={hist}
@@PHIST_IDX={hidx}
@@PNOISE={noise}
@@PERR={err}
@@PERR_SAMPLE={sample}
@@PPOS_TOTAL={pos_total}
@@PPOS_WW=0
@@PPOS_PAIR=0
@@PPUSH=0
@@PPOS_SAMPLE=
@@PWS={ws}
@@PASYNC={async_}
@@PKW_IN_CODE=1
@@PLOG_BEGIN
261017 21:03:15[0.9.7][core.heartbeat]-INFO-设备上线
261017 21:04:05[0.9.7][core.heartbeat]-INFO-心跳
@@PLOG_END
"""


def judge(label, **kv):
    rep = cp.Report()
    cp.check_logs(Fake(TPL.format(**kv)), rep, "/root/x", False)
    row = next(r for r in rep.results if r.name.startswith("L-02"))
    print(f"\n### 判定层 {label}\n    [{row.status}] {row.actual.splitlines()[0]}")
    return row


D5 = dict(ws=0, async_=0, pos_total=0)
r2 = judge("② 只有历史异常 + 预期噪声", after=72, base=907, toterr=2, hist=531, hidx=1594,
           noise=1, err=0, sample="", **D5)
assert r2.status == "PASS", r2.status
assert "data/app.log:531" in r2.actual, r2.actual
assert "历史异常 2 条位于窗口外" in r2.actual, r2.actual

r1 = judge("① 窗口内无前缀 Traceback", after=76, base=907, toterr=3, hist=531, hidx=1594,
           noise=1, err=3, sample="Traceback (most recent call last):~ModuleNotFoundError", **D5)
assert r1.status == "FAIL", r1.status

r3a = judge("③a 继承行落在窗口内", after=76, base=907, toterr=3, hist=531, hidx=1594,
            noise=0, err=1, sample="ERROR:xxx", **D5)
assert r3a.status == "FAIL", r3a.status
r3b = judge("③b 继承行落在窗口外", after=72, base=907, toterr=3, hist=531, hidx=1594,
            noise=0, err=0, sample="", **D5)

# ---------------------------------------------------------------- L-05 判定层
def j5(label, **kw):
    kv = dict(after=72, base=907, toterr=2, hist=531, hidx=1594, noise=1, err=0, sample="")
    kv.update(dict(ws=0, async_=0, pos_total=0))
    kv.update(kw)
    rep = cp.Report()
    cp.check_logs(Fake(TPL.format(**kv)), rep, "/root/x", False)
    row = next(r for r in rep.results if r.name.startswith("L-05"))
    print("### L-05 " + label)
    print(f"    [{row.status}] {row.actual.splitlines()[0][:130]}")
    return row


assert j5("无 WS 会话（心跳在线不等于 WS 在线）", ws=0).status == "WARN"
assert j5("有 WS 但拉配置失败（静默降级）", ws=3, async_=0).status == "FAIL"
assert j5("三步齐全", ws=3, async_=2, pos_total=1).status == "PASS"
assert j5("有 WS 有拉配置但没下发（device_config 可能为空）", ws=3, async_=2).status == "WARN"
assert r3b.status == "PASS", r3b.status

for p in ("_pa.awk", "_pb.awk", "_run.sh"):
    (HERE / p).unlink(missing_ok=True)
print("\nL02_REGRESSION_OK")
