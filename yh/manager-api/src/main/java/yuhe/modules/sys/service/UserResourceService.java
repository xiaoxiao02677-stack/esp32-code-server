package yuhe.modules.sys.service;

import java.util.List;
import java.util.Map;

import yuhe.common.page.PageData;

/**
 * 用户端资源服务（console-v2 顾客端 SPEC §6：/user/resources、/user/custom-models、/user/custom-voices）
 */
public interface UserResourceService {

    /**
     * 当前用户可用资源聚合：平台音色（ai_tts_voice）+ 本人审核通过的自定义音色。
     * 返回 {ttsVoices:[...]}（前端「模型为0」规则的唯一数据源）
     */
    Map<String, Object> myResources();

    // ===== 自定义模型（本人数据） =====
    PageData<Map<String, Object>> customModelPage(Map<String, Object> params);

    Map<String, Object> customModelCreate(Map<String, Object> body);

    Map<String, Object> customModelUpdate(String id, Map<String, Object> body);

    void customModelDelete(String id);

    Map<String, Object> customModelHealth(String id);

    // ===== 自定义音色（本人数据） =====
    PageData<Map<String, Object>> customVoicePage(Map<String, Object> params);

    Map<String, Object> customVoiceCreate(Map<String, Object> body);

    Map<String, Object> customVoiceUpdate(String id, Map<String, Object> body);

    void customVoiceDelete(String id);
}
