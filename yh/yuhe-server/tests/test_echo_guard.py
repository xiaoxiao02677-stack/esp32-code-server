"""echo_guard 单元测试：用 2026-10-18 COM18 实录日志的回声样本验证。

样本对照（日志时序）：
  播报: << 琳琳的脑子转不过来了        → 回声 ASR: >> 玲玲的脑子转
  播报: << 原来是在学我说话呀          → 回声 ASR: >> 原来是在学我说
  播报: << 好好好 / 都是你的话，琳琳只是个复读机
  唤醒后首交互: >> 8                    （数字碎片回声）
"""
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# tests/ 下有遮蔽用的 core/ 常规包（见 test_wake_word_threshold.py 同款说明），
# 必须把 tests/ 从 sys.path 摘掉再挂项目根，否则 import core 解析到 tests/core
_here = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _here]
sys.path.insert(0, str(_ROOT))

from core.utils.echo_guard import (  # noqa: E402
    check_echo, register_spoken_sentence, similarity, ECHO_WINDOW_S,
)


class FakeLogger:
    def bind(self, **kw):
        return self

    def info(self, msg):
        print("  [log]", msg)


class FakeConn:
    def __init__(self):
        self.logger = FakeLogger()


def test_similarity_samples():
    """日志实录回声样本的相似度（作为通道选择的参数依据）。
    注："好好好"在日志里是独立 TTS 句（与"都是你的话…"分开下发），
    比对目标是同句登记项（ratio=1.00），不是拼接长句。"""
    cases = [
        ("玲玲的脑子转", "琳琳的脑子转不过来了"),   # 同音字 + 截断（cover 0.64 → 截断通道）
        ("原来是在学我说", "原来是在学我说话呀"),   # 纯截断（cover 0.78 → 截断通道）
        ("好好好", "好好好"),                       # 整句复读（cover 1.0 → 复读通道）
    ]
    for asr, spoken in cases:
        s = similarity(asr, spoken)
        assert s >= 0.5, f"相似度不足: {asr!r} vs {spoken!r} = {s}"
        print(f"  OK 相似度 {s:.3f}: {asr!r} vs {spoken!r}")


def test_check_echo_real_log():
    """完整链路：按句子粒度登记播报句（与 send_tts_message sentence_start 一致）
    → 回声文本被拦截。样本全部来自日志实录。"""
    conn = FakeConn()
    # 日志实录的 TTS 播报句（<< 方向）
    register_spoken_sentence(conn, "一个8呀")
    register_spoken_sentence(conn, "琳琳的脑子转不过来了")
    register_spoken_sentence(conn, "好好好")
    register_spoken_sentence(conn, "都是你的话，琳琳只是个复读机")
    register_spoken_sentence(conn, "原来是在学我说话呀")

    echoes = [
        "8",                     # 日志实录：>> 8（数字碎片回声）
        "玲玲的脑子转",           # 日志实录：>> 玲玲的脑子转（同音字+截断）
        "原来是在学我说",         # 日志实录：>> 原来是在学我说（截断）
        "好好好",                 # TTS 句"好好好"的回声（整句复读）
    ]
    for e in echoes:
        assert check_echo(conn, e), f"回声漏判: {e!r}"
        print(f"  OK 拦截回声: {e!r}")


def test_short_fragment():
    """短碎片（≤2 字符）子串规则：数字回声拦截。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "一个8呀")
    assert check_echo(conn, "8"), "短碎片 '8' 未拦截"
    print("  OK 拦截短碎片: '8'")
    # 不相关短碎片放行
    assert not check_echo(conn, "嗯"), "误杀 '嗯'"
    print("  OK 放行: '嗯'")


def test_normal_user_speech_passes():
    """正常用户说话必须放行（不能误杀）。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "琳琳的脑子转不过来了")
    register_spoken_sentence(conn, "今天天气怎么样呀")
    normals = [
        "今天天气怎么样",
        "你好小智",
        "帮我开一下灯",
        "明天几点了",
        "讲个故事吧",
        "你叫什么名字",
    ]
    for n in normals:
        assert not check_echo(conn, n), f"误杀正常说话: {n!r}"
        print(f"  OK 放行正常: {n!r}")


def test_speaker_json_format():
    """带声纹 JSON 的 ASR 结果取 content 比对。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "琳琳的脑子转不过来了")
    assert check_echo(conn, '{"speaker": "主人", "content": "玲玲的脑子转"}')
    print("  OK 拦截 JSON 声纹格式回声")


def test_window_expiry():
    """窗口过期后不再比对。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "琳琳的脑子转不过来了")
    # 直接篡改时间戳模拟过期
    conn.echo_tracked_sentences[0]["t"] = time.time() - ECHO_WINDOW_S - 1
    assert not check_echo(conn, "玲玲的脑子转"), "过期窗口仍拦截"
    print("  OK 过期放行")


def test_empty_and_no_track():
    """空文本 / 无登记 → 放行不炸。"""
    conn = FakeConn()
    assert not check_echo(conn, "")
    assert not check_echo(conn, "随便说点什么")
    print("  OK 空态放行")


def test_music_mixed_full_echo():
    """2026-10-18 15:51:45 漏网案例：播放音乐时整段播报回声，
    ASR 混入幻觉字（'高'），ratio=0.949 差 0.001 没过整句复读阈值。
    长句完整复现 + ratio 分层（≥8 字放宽到 0.90）必须拦截。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "你呀，连安静都要学我一句？随你吧，")
    register_spoken_sentence(conn, "那就这么呆着，让风把话都替咱们说了。")
    echo = "你呀连安静高学我一句随你吧，那就这么呆着，让风把话都替咱们说了。"
    assert check_echo(conn, echo), "音乐混合整段回声漏判（15:51:45 案例）"
    print("  OK 拦截音乐混合整段回声")


def test_merged_multi_sentence_echo():
    """多句合并回声：整轮播报（多句）作为一条 ASR 结果回来，
    单句比对被摊薄（0.65/0.35），拼接比对整体命中（1.00）。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "刚把话都说完了，正安静呆着呢，")
    register_spoken_sentence(conn, "等着你再开口呀。")
    echo = "刚把话都说完了，正安静呆着呢，等着你再开口呀。"
    assert check_echo(conn, echo), "多句合并回声漏判（15:59:08 案例）"
    print("  OK 拦截多句合并回声")


def test_short_confirmation_not_killed():
    """确认式短应答保护：'今天天气怎么样'（7 字用户复述式接话，
    ratio=0.93）在长句分层下仍放行——长度分层只对 ≥8 字放宽。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "今天天气怎么样呀")
    assert not check_echo(conn, "今天天气怎么样"), "误杀确认式短应答"
    print("  OK 放行确认式短应答")


def test_asr_cover_channel():
    """ASR 覆盖率通道：截断型回声（cover<0.8）ratio 不足但
    ASR 内容全部来自播报句时拦截。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "一言为定，那就谁都不出声了，让歌替咱们说话。")
    echo = "一言为定，那就谁都不出声了，让哥替咱们说话。"
    assert check_echo(conn, echo), "覆盖率通道未拦截幻觉字替换回声"
    print("  OK 拦截覆盖率通道回声")


def test_pinyin_homophone_truncation():
    """拼音通道（截断+同音字）：17:51:41 打断探测漏网实录——
    ASR"被你这么夸玲玲心里还美滋"vs 播报"…琳琳…美滋滋的"，
    字符 ratio=0.77 漏网，拼音归一后 0.94 过线。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "被你这么夸，琳琳心里还美滋滋的。")
    echo = "被你这么夸玲玲心里还美滋"
    assert check_echo(conn, echo), "拼音通道未拦截同音字+截断回声"
    print("  OK 拦截拼音同音截断回声")


def test_pinyin_cross_sentence_boundary():
    """跨句拼音子串通道：18:03:30 漏网实录——播报"老人摇摇头，说 /
    我补的每一张网…"回传"摇摇头说我不"（横跨句边界 + 补→不同音），
    与任何单句 0.67/0.11、拼接整体 0.49 全漏；拼音是相邻两句拼接
    拼音串的连续子串（跨边界），必拦。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "有个老人住在海边，天天替人修渔网，补了一辈子。")
    register_spoken_sentence(conn, "有天有人问他，您这一辈子没出过海，不觉得亏吗？")
    register_spoken_sentence(conn, "老人摇摇头，说")
    register_spoken_sentence(conn, "我补的每一张网，都替我出了海")
    echo = "摇摇头说我不"
    assert check_echo(conn, echo), "跨句拼音通道未拦截句边界回声"
    print("  OK 拦截跨句边界回声")


def test_pinyin_short_confirmation_not_killed():
    """拼音通道不误杀确认式短应答："今天天气怎么样"拼音层 0.95，
    若拼音通道对短句开放会误杀——v3 设计为仅 ≥8 字长句开放拼音放宽。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "今天天气怎么样呀")
    assert not check_echo(conn, "今天天气怎么样"), "拼音通道误杀短应答"
    print("  OK 放行短应答（拼音层不对短句开放）")


def test_cross_boundary_human_speech_passes():
    """跨句通道零误杀验证：真人常见插话都不是相邻句拼接拼音的
    连续子串（对照矩阵实测全放行）。"""
    conn = FakeConn()
    register_spoken_sentence(conn, "老人摇摇头，说")
    register_spoken_sentence(conn, "我补的每一张网，都替我出了海")
    for human in ["别讲了", "停一下", "后来呢", "老人后来怎么样了", "我喜欢这个故事"]:
        assert not check_echo(conn, human), f"跨句通道误杀真人插话: {human!r}"
    print("  OK 放行真人插话（跨句通道）")


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        print(f"== {name}")
        fn()
    print("\nALL TESTS PASSED")
