"""服务端字形补字（glyph_push）接入层。

背景与契约来源：固件 main/protocols/text_glyph_payload.cc 与
managed_components/78__xiaozhi-fonts/README.md「Missing-glyph delivery」。

流程：
1. 设备在 hello 里声明 features.glyph_push=true 与 text_font{bundle,charset,size,bpp}；
2. 服务端比对文本字符与设备已装字符集（basic/common）；
3. 只把「设备没有的字形」从 full bundle 的对应 CBIN 分片里抽出来；
4. 挂到同一条文本消息的 glyph_push 字段里（tts.sentence_start / stt）；
5. 设备先用自带字体渲染，缺失字符用推送的字形做动态回退。

设计要点：
- 未声明能力的设备完全不受影响（零开销，不附加任何字段）；
- 包不存在/加载失败时静默降级，绝不因为补字影响语音主链路；
- 设备上报的 bundle/charset/size/bpp 必须与 full bundle 清单完全匹配才生效，
  避免字重/字号不一致导致的错位渲染。
"""

from pathlib import Path
import threading

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# full bundle 目录（相对服务进程工作目录），可由 config.yaml 的
# glyph_push.bundle_dir 覆盖；默认值即生产部署路径
DEFAULT_BUNDLE_DIR = "data/glyph_bundle"
MANIFEST_NAME = "manifest.json"

# 固件支持的字符集档位（text_glyph_payload.cc 只接受这两个）
SUPPORTED_CHARSETS = ("basic", "common")
SUPPORTED_BPPS = (1, 4)

_service = None
_service_lock = threading.Lock()
_service_tried = False


class GlyphPushService:
    """对 FullGlyphProvider 的薄封装（进程内单例，字体懒加载并缓存）"""

    def __init__(self, provider):
        self._provider = provider
        self.bundle = provider.bundle

    def supports(self, bundle, charset, size, bpp) -> bool:
        return self._provider.supports(bundle, charset, size, bpp)

    def payload_for_capability(self, capability: dict, text: str):
        """按设备能力生成 glyph_push 载荷；不匹配/无缺字时返回 None"""
        bundle = capability.get("bundle")
        charset = capability.get("charset")
        size = capability.get("size")
        bpp = capability.get("bpp")
        try:
            if not self.supports(bundle, charset, size, bpp):
                return None
            return self._provider.payload_for_text(text, size, bpp, charset)
        except Exception as e:  # 单条文本失败不应影响整轮对话
            logger.bind(tag=TAG).warning(f"生成字形推送载荷失败: {e}")
            return None


def _bundle_dir() -> Path:
    """字形包目录：环境变量 YUHE_GLYPH_BUNDLE_DIR 可覆盖（便于灰度/回滚）"""
    import os

    configured = os.environ.get("YUHE_GLYPH_BUNDLE_DIR")
    if configured:
        return Path(configured)
    return Path(DEFAULT_BUNDLE_DIR)


def get_service():
    """获取字形补字服务；不可用时返回 None（只尝试加载一次）"""
    global _service, _service_tried
    if _service is not None or _service_tried:
        return _service
    with _service_lock:
        if _service is not None or _service_tried:
            return _service
        _service_tried = True
        try:
            from core.utils.glyph_provider import FullGlyphProvider

            manifest = _bundle_dir() / MANIFEST_NAME
            if not manifest.is_file():
                logger.bind(tag=TAG).info(
                    f"未找到字形补字包({manifest})，glyph_push 不生效（不影响语音链路）"
                )
                return None
            _service = GlyphPushService(FullGlyphProvider(manifest))
            logger.bind(tag=TAG).info(
                f"字形补字已就绪: bundle={_service.bundle}, "
                f"字符集={sorted(_service._provider.charsets)}, "
                f"档位={sorted(_service._provider.profiles)}"
            )
        except Exception as e:
            logger.bind(tag=TAG).warning(
                f"字形补字包加载失败，glyph_push 不生效（不影响语音链路）: {e}"
            )
            _service = None
    return _service


def parse_text_font_capability(features, text_font):
    """从 hello 的 features/text_font 解析设备字形能力。

    严格对齐固件侧生成逻辑（protocol.cc AddTextFontCapabilities）：
    features.glyph_push 必须是布尔 True；text_font 必须给出 bundle/charset/size/bpp；
    size 与 bpp 为整数且 bpp ∈ {1,4}。任一条不满足即视为不支持。
    """
    if not isinstance(features, dict) or features.get("glyph_push") is not True:
        return None
    if not isinstance(text_font, dict):
        return None
    bundle = text_font.get("bundle")
    charset = text_font.get("charset")
    size = text_font.get("size")
    bpp = text_font.get("bpp")
    if not isinstance(bundle, str) or not bundle:
        return None
    if charset not in SUPPORTED_CHARSETS:
        return None
    if isinstance(size, bool) or not isinstance(size, (int, float)):
        return None
    if isinstance(bpp, bool) or not isinstance(bpp, (int, float)):
        return None
    size = int(size)
    bpp = int(bpp)
    if size <= 0 or bpp not in SUPPORTED_BPPS:
        return None
    return {"bundle": bundle, "charset": charset, "size": size, "bpp": bpp}


def attach_glyph_push(conn, message: dict, text) -> None:
    """给带文本的下行消息附加 glyph_push 字段（无能力/无缺字时静默跳过）"""
    if not text or not isinstance(message, dict):
        return
    capability = getattr(conn, "glyph_capability", None)
    if not capability:
        return
    service = get_service()
    if service is None:
        return
    payload = service.payload_for_capability(capability, text)
    if not payload:
        return
    message["glyph_push"] = payload
    try:
        conn.logger.bind(tag=TAG).info(
            f"已附带字形推送: {len(payload['glyphs'])} 字 "
            f"(bundle={payload['bundle']}, {payload['size']}_{payload['bpp']})"
        )
    except Exception:
        pass
