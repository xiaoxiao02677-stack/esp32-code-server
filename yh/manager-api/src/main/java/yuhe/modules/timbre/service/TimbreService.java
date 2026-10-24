package yuhe.modules.timbre.service;

import java.util.List;
import java.util.Map;

import yuhe.common.page.PageData;
import yuhe.common.service.BaseService;
import yuhe.modules.model.dto.VoiceDTO;
import yuhe.modules.timbre.dto.TimbreDataDTO;
import yuhe.modules.timbre.dto.TimbrePageDTO;
import yuhe.modules.timbre.entity.TimbreEntity;
import yuhe.modules.timbre.vo.TimbreDetailsVO;

/**
 * 音色的业务层的定义
 * 
 * @author zjy
 * @since 2025-3-21
 */
public interface TimbreService extends BaseService<TimbreEntity> {
    /**
     * 分页获取音色指定tts的下的音色
     * 
     * @param dto 分页查找参数
     * @return 音色列表分页数据
     */
    PageData<TimbreDetailsVO> page(TimbrePageDTO dto);

    /**
     * 获取音色指定id的详情信息
     * 
     * @param timbreId 音色表id
     * @return 音色信息
     */
    TimbreDetailsVO get(String timbreId);

    /**
     * 保存音色信息
     * 
     * @param dto 需要保存数据
     */
    void save(TimbreDataDTO dto);

    /**
     * 保存音色信息
     * 
     * @param timbreId 需要修改的id
     * @param dto      需要修改的数据
     */
    void update(String timbreId, TimbreDataDTO dto);

    /**
     * 批量删除音色
     * 
     * @param ids 需要被删除的音色id列表
     */
    void delete(String[] ids);

    List<VoiceDTO> getVoiceNames(String ttsModelId, String voiceName);

    /**
     * 获取普通音色或克隆音色配置的首个有效语言。
     *
     * @param id 音色ID
     * @return 默认语言；音色不存在或未配置有效语言时返回null
     */
    String getDefaultLanguageById(String id);

    /**
     * 根据ID获取音色名称
     * 
     * @param id 音色ID
     * @return 音色名称
     */
    String getTimbreNameById(String id);

    /**
     * 根据音色编码获取音色信息
     * 
     * @param ttsModelId 音色模型ID
     * @param voiceCode  音色编码
     * @return 音色信息
     */
    VoiceDTO getByVoiceCode(String ttsModelId, String voiceCode);

    /**
     * 探测当前引擎支持的音色并同步 DB（增/删/引用迁移）。
     *
     * 背景：百炼控制台切换 TTS 引擎后，ai_tts_voice 里的静态音色清单不会跟着变，
     * 旧音色在合成阶段报 InvalidTtsVoice（设备无声）。本方法经 yuhe-server
     * /api/tts/voice-probe 用「push2talk + transcript 文本合成」探测候选池
     * （DB 现有 + 官方 qwen-audio-3.1 全量），然后：
     * 1. 删除探测失效的系统音色（用户自建克隆音色 reference_audio 非空的不动）
     * 2. 新增不在 DB 的有效音色
     * 3. 失效音色被智能体引用时，agent.tts_voice_id 迁移到该模型首个有效音色
     *
     * @param ttsModelId TTS 模型ID（ai_model_config.id）
     * @return 探测报告（valid/invalid 列表 + 新增/删除/迁移明细）
     */
    Map<String, Object> probeAndSync(String ttsModelId);
}
