"""TTS 音色批量探测内部 API（manager-api 代理转发调用，非公开端点）。

背景：百炼控制台切换 TTS 引擎后（如 multimodal-dialog → qwen-audio-3.1），
服务端 ai_tts_voice 表里的音色不会自动跟上——旧引擎音色在合成阶段才会报
InvalidTtsVoice（Start 帧不校验音色）。本端点用「push2talk + transcript 文本
合成」探测每个音色：有效音色 ~0.4s 收到音频，无效音色 ~0.3s 返回
Error 事件（error_name=InvalidTtsVoice, code=426）。

安全模型与 tts_preview_handler 一致（design §3.1 同源）：
- ``Authorization: Bearer {server.secret}`` 服务间鉴权（常量时间比较）
- 仅由 manager-api 在同机经 127.0.0.1 调用（http_server 回环中间件防护）

POST /api/tts/voice-probe
- body: {"config_json": {百炼TTS完整配置,含type/凭据}, "voices": [{id, tts_voice}]}
  voices 为空或缺失 → 探测内置 qwen-audio-3.1 官方全量候选池（46 个）
- 响应: {"code":0, "msg":"success", "data":[{"id":"...", "tts_voice":"...", "valid":true|false, "reason":"..."}]}

并发：asyncio.Semaphore(5) 控制；单音色最长 12s 超时。
"""
import asyncio
import hmac
import json
import uuid

import websockets
from aiohttp import web

from config.logger import setup_logging
from core.api.base_handler import BaseHandler

TAG = __name__

# 探测合成文本（越短越快，仅验证音色有效性）
PROBE_TEXT = "你好"
# 探测超时（无效音色 ~0.3s 即返回 Error；兜底上限）
PROBE_TIMEOUT = 12.0
# 并发上限（百炼 WS 连接瞬时并发友好）
PROBE_CONCURRENCY = 10
# 连接建立重试（百炼偶发握手超时，实测抖动）
PROBE_CONNECT_RETRIES = 2

# qwen-audio-3.1 官方系统音色全量候选池（2026-10 官方文档
# qwen-audio-tts-voice-list；控制台切到其它引擎时探测结果即兜底验证）
CANDIDATE_POOL = [
    # 多语种与方言音色（上海/广东/东北/重庆/陕西/云南/宁波/甘肃方言+日韩法德葡意越印尼）
    {"name": "龙安灵心-知心温暖女", "tts_voice": "longanlingxin_v3.1"},
    {"name": "龙安欢-欢脱元气女", "tts_voice": "longanhuan_v3.1"},
    {"name": "龙安风悦-自然亲切女", "tts_voice": "longanfengyue_v3.1"},
    {"name": "许南川-磁性故事男", "tts_voice": "xunanchuan_v3.1"},
    # 精品中文音色（仅普通话）
    {"name": "于小云-元气亲切女", "tts_voice": "yuxiaoyun_v3.1"},
    {"name": "乔小娇-俏丽可爱女", "tts_voice": "qiaoxiaojiao_v3.1"},
    {"name": "夏小晨-元气明亮女", "tts_voice": "xiaxiaochen_v3.1"},
    {"name": "安明远-清亮自然男", "tts_voice": "anmingyuan_v3.1"},
    {"name": "温怀清-清亮柔和女", "tts_voice": "wenhuaiqing_v3.1"},
    {"name": "安小岚-清甜纯净女", "tts_voice": "anxiaolan_v3.1"},
    {"name": "谢舒柔-柔和知性女", "tts_voice": "xieshurou_v3.1"},
    {"name": "白清岚-明亮清纯女", "tts_voice": "baiqinglan_v3.1"},
    {"name": "许玉远-知性成熟女", "tts_voice": "xuyuyuan_v3.1"},
    {"name": "安若柔-气声知性女", "tts_voice": "anruorou_v3.1"},
    {"name": "闻怀之-稳重成熟女", "tts_voice": "wenhuaizhi_v3.1"},
    {"name": "萧行之-端庄贵气女", "tts_voice": "xiaoxingzhi_v3.1"},
    {"name": "顾云舒-成熟稳重女", "tts_voice": "guyunshu_v3.1"},
    {"name": "霍拙石-清亮男", "tts_voice": "huozhuoshi_v3.1"},
    {"name": "叶清禾-亲切温柔女", "tts_voice": "yeqinghe_v3.1"},
    {"name": "云欢欢-高亢热情女", "tts_voice": "yunhuanhuan_v3.1"},
    {"name": "徐小俏-自然俏皮女", "tts_voice": "xuxiaoqiao_v3.1"},
    {"name": "白安然-低沉浑厚女", "tts_voice": "baianran_v3.1"},
    {"name": "许言初-沉稳磁性女", "tts_voice": "xuyanchu_v3.1"},
    {"name": "叶知晴-轻快自然女", "tts_voice": "yezhiqing_v3.1"},
    {"name": "安迪-ABC口音男", "tts_voice": "andi_v3.1"},
    {"name": "安语晴-甜美女", "tts_voice": "anyuqing_v3.1"},
    # 精品英文音色（仅英文）
    {"name": "Emily-英式女声", "tts_voice": "Emily_v3.1"},
    {"name": "Luna-英式女声", "tts_voice": "Luna_v3.1"},
    {"name": "Eric-英式男声", "tts_voice": "Eric_v3.1"},
    {"name": "Luca-英式男声", "tts_voice": "Luca_v3.1"},
    {"name": "Abby-美式女声", "tts_voice": "Abby_v3.1"},
    {"name": "Annie-美式女声", "tts_voice": "Annie_v3.1"},
    {"name": "Ava-美式女声", "tts_voice": "Ava_v3.1"},
    {"name": "Beth-美式女声", "tts_voice": "Beth_v3.1"},
    {"name": "Betty-美式女声", "tts_voice": "Betty_v3.1"},
    {"name": "Cally-美式女声", "tts_voice": "Cally_v3.1"},
    {"name": "Cindy-美式女声", "tts_voice": "Cindy_v3.1"},
    {"name": "Donna-美式女声", "tts_voice": "Donna_v3.1"},
    {"name": "Andy-美式男声", "tts_voice": "Andy_v3.1"},
    {"name": "Brian-美式男声", "tts_voice": "Brian_v3.1"},
    {"name": "David-美式男声", "tts_voice": "David_v3.1"},
    # 其他系统音色（角色/儿童）
    {"name": "龙安元妃-高傲妃子音", "tts_voice": "longanyuanfei_v3.1"},
    {"name": "龙杰力豆-天真男童音", "tts_voice": "longjielidou_v3.1"},
    {"name": "龙安灵希-可爱甜美音", "tts_voice": "longanlingxi_v3.1"},
    {"name": "龙火火-顽皮少年音", "tts_voice": "longhuohuo_v3.1"},
    {"name": "龙应桃-温柔淡定女", "tts_voice": "longyingtao_v3.1"},
]

# 旧版 multimodal-dialog（龙系列）候选池：控制台切回该引擎时探测可复用
# （db 里历史遗留 _0001~_0030 就是这批；探出有效即保留）
LEGACY_LONG_POOL = [
    {"name": "龙小淳-知性积极女", "tts_voice": "longxiaochun_v3"},
    {"name": "龙小夏-沉稳权威女", "tts_voice": "longxiaoxia_v3"},
    {"name": "龙婉-亲和甜美女", "tts_voice": "longwan_v3"},
    {"name": "龙橙-朝气活力男", "tts_voice": "longcheng_v3"},
    {"name": "龙老铁-朴实东北男", "tts_voice": "longlaotie_v3"},
    {"name": "龙书-儒雅青年男", "tts_voice": "longshu_v3"},
    {"name": "龙硕-甜酷少女", "tts_voice": "longshuo_v3"},
    {"name": "龙悦-娇憨少女", "tts_voice": "longyue_v3"},
    {"name": "龙远-散漫青年男", "tts_voice": "longyuan_v3"},
    {"name": "龙飞-激昂解说男", "tts_voice": "longfei_v3"},
    {"name": "龙杰力豆-热血少年", "tts_voice": "longjielidou_v3"},
    {"name": "龙华-专业播音女", "tts_voice": "longhua_v3"},
    {"name": "龙强-悬疑男", "tts_voice": "longqiang_v3"},
    {"name": "龙哲-沉稳纪录片男", "tts_voice": "longzhe_v3"},
    {"name": "Bella-温柔英文女", "tts_voice": "loongbella_v3"},
]

# cosyvoice-v2 音色池（2026-10-24 对照官方文档全量整理：
# 百炼 Model Studio「CosyVoice音色列表」+ ISI「长文本合成音色列表」CosyVoice-V2 页签；
# 含无后缀的当代音色（longhuhu/longanpei/longying* 等）与 _v2 后缀音色，
# 探测按引擎实际返回判定有效性，无效自动剔除）
COSYVOICE_V2_POOL = [
    # 对话闲聊/通用
    {"name": "龙橙-智慧青年男", "tts_voice": "longcheng_v2"},
    {"name": "龙华-元气甜美女", "tts_voice": "longhua_v2"},
    {"name": "龙书-新闻男声", "tts_voice": "longshu_v2"},
    {"name": "Bella2.0-新闻女声", "tts_voice": "loongbella_v2"},
    {"name": "龙婉-积极知性女", "tts_voice": "longwan_v2"},
    {"name": "龙小淳-温柔姐姐", "tts_voice": "longxiaochun_v2"},
    {"name": "龙小夏-温柔女声", "tts_voice": "longxiaoxia_v2"},
    # 教育/短视频配音
    {"name": "龙安培-青少年教师女", "tts_voice": "longanpei"},
    {"name": "龙黛玉-娇率才女音", "tts_voice": "longdaiyu"},
    {"name": "龙高僧-得道高僧音", "tts_voice": "longgaoseng"},
    # 客服
    {"name": "龙应沐-优雅知性女", "tts_voice": "longyingmu"},
    {"name": "龙应询-年轻青涩男", "tts_voice": "longyingxun"},
    {"name": "龙应催-严肃催收男", "tts_voice": "longyingcui"},
    {"name": "龙应答-开朗高音女", "tts_voice": "longyingda"},
    {"name": "龙应静-低调冷静女", "tts_voice": "longyingjing"},
    {"name": "龙应严-义正严辞女", "tts_voice": "longyingyan"},
    {"name": "龙应甜-温柔甜美女", "tts_voice": "longyingtian"},
    {"name": "龙应冰-尖锐强势女", "tts_voice": "longyingbing"},
    {"name": "龙应桃-温柔淡定女", "tts_voice": "longyingtao"},
    {"name": "龙应聆-温和共情女", "tts_voice": "longyingling"},
    # 语音助手/直播带货
    {"name": "YUMI-正经青年女", "tts_voice": "longyumi_v2"},
    {"name": "龙安燃-活泼质感女", "tts_voice": "longanran"},
    {"name": "龙安宣-经典直播女", "tts_voice": "longanxuan"},
    {"name": "龙安冲-激情推销男", "tts_voice": "longanchong"},
    {"name": "龙安萍-高亢直播女", "tts_voice": "longanping"},
    # 有声书
    {"name": "龙白芷-睿气旁白女", "tts_voice": "longbaizhi"},
    {"name": "龙三叔-沉稳质感男", "tts_voice": "longsanshu"},
    {"name": "龙修-博才说书男", "tts_voice": "longxiu_v2"},
    {"name": "龙妙-抑扬顿挫女", "tts_voice": "longmiao_v2"},
    {"name": "龙悦-温暖磁性女", "tts_voice": "longyue_v2"},
    {"name": "龙楠-睿智青年男", "tts_voice": "longnan_v2"},
    {"name": "龙媛-温暖治愈女", "tts_voice": "longyuan_v2"},
    # 社交陪伴
    {"name": "龙安柔-温柔闺蜜女", "tts_voice": "longanrou"},
    {"name": "龙嫱-浪漫风情女", "tts_voice": "longqiang_v2"},
    {"name": "龙寒-温暖痴情男", "tts_voice": "longhan_v2"},
    {"name": "龙星-温婉邻家女", "tts_voice": "longxing_v2"},
    {"name": "龙菲菲-甜美娇气女", "tts_voice": "longfeifei_v2"},
    {"name": "龙小诚-磁性低音男", "tts_voice": "longxiaocheng_v2"},
    {"name": "龙哲-呆板大暖男", "tts_voice": "longzhe_v2"},
    {"name": "龙颜-温暖春风女", "tts_voice": "longyan_v2"},
    {"name": "龙天-磁性理智男", "tts_voice": "longtian_v2"},
    {"name": "龙泽-温暖元气男", "tts_voice": "longze_v2"},
    {"name": "龙邵-积极向上男", "tts_voice": "longshao_v2"},
    {"name": "龙浩-多情忧郁男", "tts_voice": "longhao_v2"},
    {"name": "龙深-实力歌手男", "tts_voice": "kabuleshen_v2"},
    # 童声
    {"name": "龙呼呼-天真烂漫女童", "tts_voice": "longhuhu"},
    {"name": "龙杰力豆-阳光顽皮男", "tts_voice": "longjielidou_v2"},
    {"name": "龙铃-稚气呆板女", "tts_voice": "longling_v2"},
    {"name": "龙可-懵懂乖乖女", "tts_voice": "longke_v2"},
    {"name": "龙仙-豪放可爱女", "tts_voice": "longxian_v2"},
    {"name": "龙汪汪-台湾少年音", "tts_voice": "longwangwang"},
    {"name": "龙泡泡-飞天泡泡音", "tts_voice": "longpaopao"},
    {"name": "龙闪闪-戏剧化童声", "tts_voice": "longshanshan"},
    {"name": "龙牛牛-阳光男童声", "tts_voice": "longniuniu"},
    # 方言
    {"name": "龙老铁-东北直率男", "tts_voice": "longlaotie_v2"},
    {"name": "龙嘉怡-知性粤语女", "tts_voice": "longjiayi_v2"},
    {"name": "龙桃-积极粤语女", "tts_voice": "longtao_v2"},
    # 诗词朗诵/新闻播报
    {"name": "龙飞-热血磁性男", "tts_voice": "longfei_v2"},
    {"name": "李白-古代诗仙男", "tts_voice": "libai_v2"},
    {"name": "龙津-优雅温润男", "tts_voice": "longjin_v2"},
    {"name": "龙硕-博才干练男", "tts_voice": "longshuo_v2"},
    {"name": "龙小白-沉稳播报女", "tts_voice": "longxiaobai_v2"},
]


def _json_error(status: int, msg: str) -> web.Response:
    return web.json_response({"code": status, "msg": msg, "data": None}, status=status)


class _InvalidVoiceError(Exception):
    """确定性音色无效（InvalidTtsVoice 等），不需重试。"""


class _TransientError(Exception):
    """临时性错误（限流/内部错误/网络抖动），值得重试。"""


class TtsVoiceProbeHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        # 与 memory_handler 相同的 auth_key（app.py 已解析进 config["server"]["auth_key"]）
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    async def handle_probe(self, request) -> web.Response:
        if not self._verify_auth(request):
            return _json_error(401, "未授权")

        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "请求体必须为 JSON")
        if not isinstance(body, dict) or not body.get("config_json"):
            return _json_error(400, "请求体缺少 config_json 字段")

        config_json = body["config_json"]
        if not isinstance(config_json, dict) or not config_json.get("type"):
            return _json_error(400, "config_json 缺少 type 字段")
        if config_json.get("type") != "aliyun_multimodal":
            return _json_error(400, f"暂不支持该TTS类型探测: {config_json.get('type')}")

        voices = body.get("voices") or []
        include_pool = body.get("include_pool", True)  # 默认合并官方候选池全量探测
        seen = set()
        probe_items = []
        for v in voices:
            if isinstance(v, dict) and v.get("tts_voice") and v["tts_voice"] not in seen:
                seen.add(v["tts_voice"])
                probe_items.append({"id": v.get("id"), "tts_voice": v["tts_voice"], "name": v.get("name", "")})
        # 候选池始终合并（引擎无关全量并集：3.1 池 + v2 池 + 遗留 v3 池；
        # 探测按当前引擎实际返回判有效/失效，不同引擎间自动适配）
        if include_pool:
            for pool in (CANDIDATE_POOL, COSYVOICE_V2_POOL, LEGACY_LONG_POOL):
                for c in pool:
                    if c["tts_voice"] not in seen:
                        seen.add(c["tts_voice"])
                        probe_items.append({"id": None, "tts_voice": c["tts_voice"], "name": c["name"]})

        sem = asyncio.Semaphore(PROBE_CONCURRENCY)

        async def probe_one(item):
            async with sem:
                valid, reason = await self._probe_voice(config_json, item["tts_voice"])
                return {
                    "id": item.get("id"),
                    "name": item.get("name", ""),
                    "tts_voice": item["tts_voice"],
                    "valid": valid,
                    "reason": reason,
                }

        results = await asyncio.gather(*(probe_one(it) for it in probe_items))
        return web.json_response({"code": 0, "msg": "success", "data": results})

    async def _probe_voice(self, config_json: dict, voice: str):
        """push2talk + transcript 合成探测单个音色。

        有效 → 收到二进制音频帧；无效 → Error 事件 InvalidTtsVoice。
        """
        ws_url = config_json.get("ws_url") or "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"
        api_key = config_json.get("api_key") or ""
        app_id = config_json.get("app_id") or ""
        workspace_id = config_json.get("workspace_id") or ""
        if not api_key or not app_id:
            return False, "配置缺少 api_key/app_id"

        task_id = str(uuid.uuid4())
        start_msg = {
            "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "task_group": "aigc",
                "task": "multimodal-generation",
                "function": "generation",
                "model": "multimodal-dialog",
                "input": {"directive": "Start", "workspace_id": workspace_id, "app_id": app_id},
                "parameters": {
                    "upstream": {"type": "AudioOnly", "mode": "push2talk", "audio_format": "pcm", "sample_rate": 16000},
                    "downstream": {"voice": voice, "sample_rate": 24000, "audio_format": "pcm"},
                    "client_info": {"user_id": "yuhe-voice-probe"},
                },
            },
        }
        last_error = None
        for attempt in range(PROBE_CONNECT_RETRIES + 1):
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers={"Authorization": f"bearer {api_key}"},
                    user_agent_header="yuhe-probe/1.0",
                    open_timeout=10,
                    close_timeout=3,
                ) as ws:
                    return await self._probe_round(ws, task_id, app_id, start_msg)
            except _InvalidVoiceError as e:
                return False, str(e)
            except _TransientError as e:
                # 限流/内部错误：指数退避后重试（1s/2s）
                last_error = str(e)
                if attempt < PROBE_CONNECT_RETRIES:
                    await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                # 握手超时等网络抖动：重试后仍失败才判 invalid
                last_error = f"连接异常: {str(e)[:120]}"
        return False, last_error

    async def _probe_round(self, ws, task_id, app_id, start_msg):
        """单轮探测（连接已建立）：听事件直到有效/无效结论。"""
        await ws.send(json.dumps(start_msg))
        dialog_id = None
        sent = False
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=PROBE_TIMEOUT)
            except asyncio.TimeoutError:
                return False, "超时无响应"
            if isinstance(raw, bytes):
                return True, ""
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            out = (msg.get("payload") or {}).get("output") or {}
            ev = out.get("event", "")
            if ev == "Started":
                dialog_id = out.get("dialog_id")
            elif ev == "DialogStateChanged" and out.get("state") == "Listening" and not sent:
                sent = True
                await ws.send(json.dumps({
                    "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {
                        "task_group": "aigc",
                        "task": "multimodal-generation",
                        "function": "generation",
                        "model": "multimodal-dialog",
                        "input": {
                            "app_id": app_id,
                            "directive": "RequestToRespond",
                            "dialog_id": dialog_id,
                            "type": "transcript",
                            "text": PROBE_TEXT,
                        },
                    },
                }))
            elif ev == "Error":
                # 音色错误（InvalidTtsVoice）确定性失败不重试；
                # 限流/内部错误（Throttling/InternalSynthesizerError）抛通用异常走重试
                name = str(out.get("error_name", ""))
                if "InvalidTtsVoice" in name:
                    raise _InvalidVoiceError(f"{name}: {out.get('error_message', '')[:160]}")
                raise _TransientError(f"{name}: {out.get('error_message', '')[:160]}")
            elif ev == "TaskFailed":
                raise _TransientError(f"TaskFailed: {str(out.get('message', out.get('code', '')))[:160]}")
