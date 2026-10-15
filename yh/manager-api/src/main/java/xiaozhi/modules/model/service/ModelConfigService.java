package xiaozhi.modules.model.service;

import java.util.List;
import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.model.dto.LlmModelBasicInfoDTO;
import xiaozhi.modules.model.dto.ModelBasicInfoDTO;
import xiaozhi.modules.model.dto.ModelConfigBodyDTO;
import xiaozhi.modules.model.dto.ModelConfigDTO;
import xiaozhi.modules.model.entity.ModelConfigEntity;

public interface ModelConfigService extends BaseService<ModelConfigEntity> {

    List<ModelBasicInfoDTO> getModelCodeList(String modelType, String modelName);

    List<LlmModelBasicInfoDTO> getLlmModelCodeList(String modelName);

    PageData<ModelConfigDTO> getPageList(String modelType, String modelName, String page, String limit);

    ModelConfigDTO add(String modelType, String provideCode, ModelConfigBodyDTO modelConfigBodyDTO);

    ModelConfigDTO edit(String modelType, String provideCode, String id, ModelConfigBodyDTO modelConfigBodyDTO);

    void delete(String id);

    /**
     * 根据ID获取模型名称
     *
     * @param id 模型ID
     * @return 模型名称
     */
    String getModelNameById(String id);

    /**
     * 根据ID获取模型的 TTS 配置类型（config_json.type）
     *
     * @param id 模型ID
     * @return 配置类型（如 doubao_v3 / edge / qwen_tts），模型不存在或未配置时返回 null
     */
    String getProviderType(String id);

    /**
     * 根据ID获取模型原始配置 JSON（明文，仅限服务间内部调用如 TTS 试听）
     *
     * @param id 模型ID
     * @return config_json 字符串，模型不存在时返回 null
     */
    String getRawConfigJson(String id);

    /**
     * 根据ID获取模型配置
     * 
     * @param id 模型ID
     * @return 模型配置实体
     */
    ModelConfigEntity getModelByIdFromCache(String id);

    /**
     * 设置默认模型
     *
     * @param modelType 模型类型
     * @param isDefault 是否默认（1:是，0:否）
     */
    void setDefaultModel(String modelType, int isDefault);

    /**
     * 获取符合条件的TTS平台列表
     *
     * @return TTS平台列表(id和modelName)
     */
    List<Map<String, Object>> getTtsPlatformList();

    /**
     * 根据模型类型获取所有启用的模型配置
     *
     * @param modelType 模型类型（如：LLM, TTS, ASR等）
     * @return 启用的模型配置列表
     */
    List<ModelConfigEntity> getEnabledModelsByType(String modelType);

    /**
     * 统计 Intent/Memory 类型模型配置的 config_json 中引用指定 LLM 的行数
     *
     * @param modelId LLM 模型ID
     * @return 引用行数
     */
    long countConfigJsonLlmReference(String modelId);
}
