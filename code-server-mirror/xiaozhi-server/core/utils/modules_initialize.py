from typing import Dict, Any
from config.logger import setup_logging
from core.utils import tts, llm, intent, memory, vad, asr

TAG = __name__
logger = setup_logging()


def _make_safe_init_sandbox(modules, *triples):
    """测试/复用辅助：对若干 (module_key, selected_name, factory) 三元组执行隔离初始化。

    每个三元组的失败只影响自身 key，不中断其他组件。
    """
    for i in range(0, len(triples), 3):
        module_key, selected_name, factory = triples[i], triples[i + 1], triples[i + 2]
        try:
            modules[module_key] = factory()
            logger.bind(tag=TAG).info(f"初始化组件: {module_key}成功 {selected_name}")
        except Exception as e:
            modules[module_key] = None
            logger.bind(tag=TAG).error(
                f"初始化组件: {module_key}失败 {selected_name}, 原因: {e}（该组件已跳过）"
            )
    return modules


def initialize_modules(
    logger,
    config: Dict[str, Any],
    init_vad=False,
    init_asr=False,
    init_llm=False,
    init_tts=False,
    init_memory=False,
    init_intent=False,
) -> Dict[str, Any]:
    """
    初始化所有模块组件

    Args:
        config: 配置字典

    Returns:
        Dict[str, Any]: 包含所有初始化后的模块的字典
    """
    modules = {}

    def _safe_init(module_key, selected_name, factory):
        """单模块隔离初始化：失败不拖垮其他组件（如 LLM 配置坏时 TTS/ASR 应照常工作）。

        Args:
            module_key: modules 字典键（tts/llm/intent/memory/vad/asr）
            selected_name: 选中的模块 ID（用于日志）
            factory: 无参可调用，内部完成 create_instance 并返回实例
        Returns:
            初始化后的实例；失败返回 None
        """
        try:
            instance = factory()
            modules[module_key] = instance
            logger.bind(tag=TAG).info(f"初始化组件: {module_key}成功 {selected_name}")
            return instance
        except Exception as e:
            modules[module_key] = None
            logger.bind(tag=TAG).error(
                f"初始化组件: {module_key}失败 {selected_name}, 原因: {e}（该组件已跳过，连接将沿用既有实例或服务默认值）"
            )
            return None

    # 初始化TTS模块
    if init_tts:
        select_tts_module = config["selected_module"]["TTS"]
        _safe_init("tts", select_tts_module, lambda: initialize_tts(config))

    # 初始化LLM模块
    if init_llm:
        select_llm_module = config["selected_module"]["LLM"]
        llm_type = (
            select_llm_module
            if "type" not in config["LLM"][select_llm_module]
            else config["LLM"][select_llm_module]["type"]
        )
        _safe_init(
            "llm",
            select_llm_module,
            lambda: llm.create_instance(
                llm_type,
                config["LLM"][select_llm_module],
            ),
        )

    # 初始化Intent模块
    if init_intent:
        select_intent_module = config["selected_module"]["Intent"]
        intent_type = (
            select_intent_module
            if "type" not in config["Intent"][select_intent_module]
            else config["Intent"][select_intent_module]["type"]
        )
        _safe_init(
            "intent",
            select_intent_module,
            lambda: intent.create_instance(
                intent_type,
                config["Intent"][select_intent_module],
            ),
        )

    # 初始化Memory模块
    if init_memory:
        select_memory_module = config["selected_module"]["Memory"]
        memory_type = (
            select_memory_module
            if "type" not in config["Memory"][select_memory_module]
            else config["Memory"][select_memory_module]["type"]
        )
        _safe_init(
            "memory",
            select_memory_module,
            lambda: memory.create_instance(
                memory_type,
                config["Memory"][select_memory_module],
                config.get("summaryMemory", None),
            ),
        )

    # 初始化VAD模块
    if init_vad:
        select_vad_module = config["selected_module"]["VAD"]
        vad_type = (
            select_vad_module
            if "type" not in config["VAD"][select_vad_module]
            else config["VAD"][select_vad_module]["type"]
        )
        _safe_init(
            "vad",
            select_vad_module,
            lambda: vad.create_instance(
                vad_type,
                config["VAD"][select_vad_module],
            ),
        )

    # 初始化ASR模块
    if init_asr:
        select_asr_module = config["selected_module"]["ASR"]
        _safe_init("asr", select_asr_module, lambda: initialize_asr(config))
    return modules


def initialize_tts(config):
    select_tts_module = config["selected_module"]["TTS"]
    tts_config = config["TTS"][select_tts_module].copy()
    tts_config.setdefault("tts_timeout", config.get("tts_timeout", 15))
    tts_type = (
        select_tts_module
        if "type" not in tts_config
        else tts_config["type"]
    )
    new_tts = tts.create_instance(
        tts_type,
        tts_config,
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    return new_tts


def initialize_asr(config):
    select_asr_module = config["selected_module"]["ASR"]
    asr_type = (
        select_asr_module
        if "type" not in config["ASR"][select_asr_module]
        else config["ASR"][select_asr_module]["type"]
    )
    new_asr = asr.create_instance(
        asr_type,
        config["ASR"][select_asr_module],
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    logger.bind(tag=TAG).info("ASR模块初始化完成")
    return new_asr


def initialize_voiceprint(asr_instance, config):
    """初始化声纹识别功能"""
    voiceprint_config = config.get("voiceprint")
    if not voiceprint_config:
        return False  

    # 应用配置
    if not voiceprint_config.get("url") or not voiceprint_config.get("speakers"):
        logger.bind(tag=TAG).warning("声纹识别配置不完整")
        return False
        
    try:
        asr_instance.init_voiceprint(voiceprint_config)
        logger.bind(tag=TAG).info("ASR模块声纹识别功能已动态启用")
        logger.bind(tag=TAG).info(f"配置说话人数量: {len(voiceprint_config['speakers'])}")
        return True
    except Exception as e:
        logger.bind(tag=TAG).error(f"动态初始化声纹识别功能失败: {str(e)}")
        return False
