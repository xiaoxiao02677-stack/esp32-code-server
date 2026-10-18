"""回声防自触发（设备自言自语防护）。

背景：无回采通道（非 AEC）版型的播报尾音会被麦克风拾取并回传（日志表现：
`<< 琳琳的脑子转不过来了` 播放 → `>> 玲玲的脑子转` 回传），ASR 把回声转成
"用户说话"进对话流，AI 回应回声、回应又被回声……形成自言自语循环
（实测日志中 AI 自己都说"都是你的话，琳琳只是个复读机"）。

方案：服务端把每轮 TTS 播报的句子文本登记在连接上（带时间戳滑动窗口），
ASR 出文本后先与"窗口内播报过的句子"比对——相似即判定回声，丢弃不进
startToChat。对 AEC 设备同样生效（AEC 衰减后仍偶发漏网），对非 AEC 设备
是决定性防护。

相似度算法：difflib.SequenceMatcher 字符相似率。选它而不是 trigram/编辑距离
的原因：回声经 ASR 常出现**同音字替换**（琳琳→玲玲）+ 截断（不过来了→转），
SequenceMatcher 对替换和截断都鲁棒（最长公共子序列思想），且是标准库。

误杀权衡：用户复述设备刚说的话（如确认式"好的"/"开灯"）会被判回声丢弃。
代价是丢一句无关紧要的搭话；收益是斩断自言自语循环——两者不对等，倾向拦截。
"""

import json
import time
import re
from difflib import SequenceMatcher

TAG = __name__

# 登记窗口：句子播报后保留这么久用于比对（秒）。
# 覆盖"下发 → 播放 → 回声拾取 → 上行 → VAD 归零 → ASR 成文"全程延迟。
# 实测回声在句子 sentence_start 后 ~3-13s 内回来（含 10s 长句），30s 留足余量。
ECHO_WINDOW_S = 30.0

# 相似度阈值（SequenceMatcher.ratio，0~1）。
# 实测样本："玲玲的脑子转" vs "琳琳的脑子转不过来了" = 0.50；
# "原来是在学我说" vs "原来是在学我说话呀" = 0.88；
# "好好好"（整句复读） vs "好好好" = 1.00。
# 误杀样本："今天天气怎么样"（用户问）vs "今天天气怎么样呀"（播报）= 0.93——
# 完整复述型。区分手段见下方 ECHO_COVER_RATIO（覆盖率规则）。
ECHO_SIMILARITY_THRESHOLD = 0.5

# 覆盖率分界：ASR 长度 / 播报句长度 ≥ 此值视为"完整复述"。
# 实测回声多为截断（cover 0.64/0.78），复述型误杀是近乎完整的（0.875）。
# 完整复述里只拦"逐字级复读"（ratio≥0.95，如回声样本"好好好"=1.00），
# 而用户自然接话的近似句（"今天天气怎么样" vs "…怎么样呀" = 0.93）放行。
ECHO_COVER_RATIO = 0.8
ECHO_FULL_REPEAT_RATIO = 0.95

# ASR 短碎片（≤2 字符，如 "8"）单独走"包含"规则：是某句播报文本的子串即判回声。
# 声学噪声常被 ASR 成单字碎片，而单字恰是上一轮播报内容（数字/语气词）的
# 情况几乎只有回声一种解释。
ECHO_SHORT_MAX_LEN = 2

# 登记句子数上限（防超长播报轮次撑爆内存）
MAX_TRACKED_SENTENCES = 20

_NON_HAN_OR_ALNUM = re.compile(r"[^\w\u4e00-\u9fff]+")


def _normalize(text: str) -> str:
    """去标点/空白/emoji，只留有效字符（汉字/字母/数字），小写。"""
    return _NON_HAN_OR_ALNUM.sub("", str(text or "")).lower()


def _extract_content(text: str) -> str:
    """带声纹的 ASR 结果是 {"speaker":..,"content":..} JSON——取 content 比对，
    避免 JSON 键名（speaker/content 等字母）污染相似度计算。"""
    s = str(text or "").strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            data = json.loads(s)
            if isinstance(data, dict) and data.get("content"):
                return str(data["content"])
        except (json.JSONDecodeError, ValueError):
            pass
    return s


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def register_spoken_sentence(conn, text: str) -> None:
    """登记一句即将播报的 TTS 文本（send_tts_message sentence_start 时调用）。"""
    norm = _normalize(text)
    if not norm:
        return
    if not hasattr(conn, "echo_tracked_sentences"):
        conn.echo_tracked_sentences = []
    conn.echo_tracked_sentences.append({"t": time.time(), "text": norm})
    # 趁手裁剪超量（过期项在 check 时惰性跳过）
    if len(conn.echo_tracked_sentences) > MAX_TRACKED_SENTENCES:
        conn.echo_tracked_sentences = conn.echo_tracked_sentences[-MAX_TRACKED_SENTENCES:]


def check_echo(conn, asr_text: str) -> bool:
    """判断 ASR 文本是否为设备自播报的回声。

    返回 True = 判定回声（丢弃）；False = 放行进正常对话。
    任何内部异常都放行（防护模块绝不阻断主链路）。
    """
    try:
        tracked = getattr(conn, "echo_tracked_sentences", None)
        if not tracked:
            return False
        norm = _normalize(_extract_content(asr_text))
        if not norm:
            return False
        now = time.time()
        for item in tracked:
            if now - item["t"] > ECHO_WINDOW_S:
                continue
            spoken = item["text"]
            # 短碎片：是播报文本的子串即回声（如上一轮说 "…8…" 回传 "8"）
            if len(norm) <= ECHO_SHORT_MAX_LEN:
                if norm in spoken:
                    conn.logger.bind(tag=TAG).info(
                        f"回声拦截(短碎片): ASR『{asr_text}』 ⊂ 播报句，丢弃"
                    )
                    return True
                continue
            if len(norm) < 3:
                continue
            # 常规比对：字符相似率（对同音字替换/截断鲁棒）。
            # 完整复述（覆盖率高）单独处理：用户听完播报后自然接话/追问时
            # 常与播报句部分重合（"今天天气怎么样呀"→"今天天气怎么样"），
            # 只拦"几乎逐字复读"（ratio≥0.9，同音字级差异）；
            # 截断型回声（覆盖率低）走 0.5 宽阈值。
            ratio = similarity(norm, spoken)
            cover = len(norm) / len(spoken) if spoken else 0
            if cover >= ECHO_COVER_RATIO:
                if ratio >= ECHO_FULL_REPEAT_RATIO:
                    conn.logger.bind(tag=TAG).info(
                        f"回声拦截(整句复读): ASR『{asr_text}』与播报句相似 "
                        f"({ratio:.2f})，丢弃"
                    )
                    return True
            else:
                if ratio >= ECHO_SIMILARITY_THRESHOLD:
                    conn.logger.bind(tag=TAG).info(
                        f"回声拦截: ASR『{asr_text}』与播报句相似 "
                        f"({ratio:.2f})，丢弃"
                    )
                    return True
        return False
    except Exception:
        return False
