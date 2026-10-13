package xiaozhi.modules.sys.controller;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.service.DisplayConfigService;
import xiaozhi.modules.sys.service.UserDefaultService;
import xiaozhi.modules.timbre.dao.TimbreDao;
import xiaozhi.modules.timbre.entity.TimbreEntity;

/**
 * 用户端资源聚合（模型为0规则的数据源）
 * <p>
 * data={llmModels, ttsVoices, defaults, displayConfig}：
 * - llmModels = 平台启用 LLM（model_type 大写比较）+ 本人审核通过的自定义 LLM
 * - ttsVoices = 平台音色 + 本人通过的自定义音色
 * - defaults = 三级继承合并后的默认配置
 * - displayConfig = 三级继承合并后的字段展示配置
 * </p>
 */
@AllArgsConstructor
@RestController
@Tag(name = "用户端资源")
public class UserResourceController {

    private final ModelConfigService modelConfigService;
    private final TimbreDao timbreDao;
    private final UserDefaultService userDefaultService;
    private final DisplayConfigService displayConfigService;
    private final xiaozhi.modules.sys.service.UserCustomModelService userCustomModelService;
    private final xiaozhi.modules.sys.service.UserCustomVoiceService userCustomVoiceService;

    @GetMapping("/user/resources")
    @Operation(summary = "用户端可用资源聚合（模型/音色/默认配置/展示配置）")
    public Result<Map<String, Object>> myResources() {
        Long userId = SecurityUser.getUserId();

        Map<String, Object> data = new LinkedHashMap<>();

        // 1) 平台启用 LLM
        LambdaQueryWrapper<ModelConfigEntity> llmWrapper = new LambdaQueryWrapper<>();
        llmWrapper.eq(ModelConfigEntity::getModelType, "LLM");
        llmWrapper.eq(ModelConfigEntity::getIsEnabled, 1);
        List<ModelConfigEntity> platformLlm = modelConfigService.list(llmWrapper);

        List<Map<String, Object>> llmModels = new ArrayList<>();
        for (ModelConfigEntity m : platformLlm) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", m.getId());
            item.put("modelName", m.getModelName());
            item.put("source", "platform");
            llmModels.add(item);
        }

        // 2) 本人审核通过的自定义 LLM
        try {
            List<Map<String, Object>> customLlm = userCustomModelService.listApprovedAsResources(userId, "LLM");
            llmModels.addAll(customLlm);
        } catch (Exception ignore) {
        }

        data.put("llmModels", llmModels);

        // 3) 平台音色
        List<TimbreEntity> platformVoices = timbreDao.selectList(new LambdaQueryWrapper<>());
        List<Map<String, Object>> ttsVoices = new ArrayList<>();
        for (TimbreEntity v : platformVoices) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", v.getId());
            item.put("name", v.getName());
            item.put("ttsModelId", v.getTtsModelId());
            item.put("source", "platform");
            ttsVoices.add(item);
        }

        // 4) 本人审核通过的自定义音色
        try {
            List<Map<String, Object>> customVoices = userCustomVoiceService.listApprovedAsResources(userId);
            ttsVoices.addAll(customVoices);
        } catch (Exception ignore) {
        }

        data.put("ttsVoices", ttsVoices);

        // 5) defaults / displayConfig（三级继承合并）
        data.put("defaults", userDefaultService.getEffectiveForUser(userId));
        data.put("displayConfig", displayConfigService.getEffectiveForUser(userId));

        return new Result<Map<String, Object>>().ok(data);
    }
}
