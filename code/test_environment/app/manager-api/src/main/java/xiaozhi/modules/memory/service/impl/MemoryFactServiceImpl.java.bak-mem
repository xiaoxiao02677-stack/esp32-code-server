package xiaozhi.modules.memory.service.impl;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import cn.hutool.json.JSONObject;
import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.agent.dto.AgentDTO;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.memory.client.MemoryInternalClient;
import xiaozhi.modules.memory.dto.MemoryFactDTO;
import xiaozhi.modules.memory.service.MemoryFactService;
import xiaozhi.modules.memory.vo.FeedbackVO;
import xiaozhi.modules.memory.vo.MemoryAgentVO;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;

/**
 * 记忆条目管理服务实现：引擎分派（design §5.2）
 * - mem_holographic：代理 xiaozhi-server 内部管理 API（与设备对话读写同一把锁）
 * - mem0ai：平台账号记忆，无信任分/状态体系（P0 降级为"未配置提示"）
 * - mem_local_short：压缩档案式记忆，不支持条目管理，返回友好提示
 * - nomem / mem_report_only：空列表
 */
@Slf4j
@Service
@AllArgsConstructor
public class MemoryFactServiceImpl implements MemoryFactService {

    /** 引擎类型：Holographic 本地记忆（内部 API 代理） */
    private static final String ENGINE_MEM_HOLOGRAPHIC = "mem_holographic";
    /** 引擎类型：Mem0AI 平台记忆 */
    private static final String ENGINE_MEM0AI = "mem0ai";
    /** 引擎类型：本地短记忆（压缩档案） */
    private static final String ENGINE_MEM_LOCAL_SHORT = "mem_local_short";

    private final MemoryInternalClient memoryInternalClient;
    private final AgentService agentService;
    private final ModelConfigService modelConfigService;

    @Override
    public List<MemoryAgentVO> listAgents(Long userId) {
        List<AgentDTO> userAgents = agentService.getUserAgents(userId, null, "name");
        if (userAgents == null || userAgents.isEmpty()) {
            return Collections.emptyList();
        }
        List<MemoryAgentVO> result = new ArrayList<>();
        for (AgentDTO agent : userAgents) {
            if (StringUtils.isBlank(agent.getMemModelId())) {
                continue;
            }
            String engine = resolveEngineTypeByModelId(agent.getMemModelId());
            // 无条目化能力的引擎不展示：nomem 无记忆；mem_report_only 只上报不存储；powermem 为上游场外存量（G-4/G-10，按解析后 engine 过滤，覆盖自建模型 ID 场景）
            if ("nomem".equals(engine) || "mem_report_only".equals(engine) || "powermem".equals(engine)) {
                continue;
            }
            MemoryAgentVO vo = new MemoryAgentVO();
            vo.setAgentId(agent.getId());
            vo.setName(agent.getAgentName());
            vo.setEngine(engine);
            vo.setMemModelId(agent.getMemModelId());
            vo.setAvailable(resolveEngineAvailable(agent.getMemModelId(), vo.getEngine()));
            vo.setFactCount(0);
            vo.setPendingCount(0);
            result.add(vo);
        }
        if (result.isEmpty()) {
            return result;
        }
        // holographic 引擎的条目统计来自内部服务，一次性获取；服务异常时保持 0 并降级记录日志
        boolean hasHolographic = result.stream().anyMatch(vo -> ENGINE_MEM_HOLOGRAPHIC.equals(vo.getEngine()));
        if (!hasHolographic) {
            return result;
        }
        List<Map<String, Object>> internalAgents = null;
        try {
            Map<String, Object> resp = memoryInternalClient.get("/agents", null);
            internalAgents = JsonUtils.toStringObjectMapList(resp.get("data"));
        } catch (Exception e) {
            log.error("获取记忆 Agent 统计失败: {}", e.getMessage());
        }
        if (internalAgents == null || internalAgents.isEmpty()) {
            return result;
        }
        for (MemoryAgentVO vo : result) {
            if (!ENGINE_MEM_HOLOGRAPHIC.equals(vo.getEngine())) {
                continue;
            }
            for (Map<String, Object> item : internalAgents) {
                if (vo.getAgentId().equals(item.get("agent_id"))) {
                    vo.setFactCount(toInteger(item.get("fact_count")));
                    vo.setPendingCount(toInteger(item.get("pending_count")));
                    break;
                }
            }
        }
        return result;
    }

    @Override
    public PageData<MemoryFactDTO> getFactPage(String agentId, String keyword, String category, String status,
            Double trustMin, Double trustMax, String start, String end, Integer page, Integer size,
            String sortBy, String order, Long userId) {
        if (StringUtils.isBlank(agentId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(agentId, userId);

        String engine = resolveEngineType(agentId, userId);
        if (!ENGINE_MEM_HOLOGRAPHIC.equals(engine)) {
            if (ENGINE_MEM_LOCAL_SHORT.equals(engine)) {
                throw new RenException("该引擎为压缩档案式记忆，暂不支持条目管理，可切换至 Holographic 引擎");
            }
            if (ENGINE_MEM0AI.equals(engine)) {
                throw new RenException("mem0 平台记忆暂不支持条目管理（未配置 API Key 或功能建设中）");
            }
            if ("powermem".equals(engine)) {
                throw new RenException("PowerMem 云端记忆暂不支持控制台条目管理");
            }
            // nomem / mem_report_only 等无记忆引擎
            return new PageData<>(Collections.emptyList(), 0);
        }

        int safePage = page == null || page < 1 ? 1 : page;
        int safeSize = size == null || size < 1 ? 20 : Math.min(size, 100);

        Map<String, Object> query = new HashMap<>();
        if (StringUtils.isNotBlank(keyword)) {
            query.put("keyword", keyword);
        }
        if (StringUtils.isNotBlank(category)) {
            query.put("category", category);
        }
        if (StringUtils.isNotBlank(status)) {
            query.put("status", status);
        }
        if (trustMin != null) {
            query.put("trust_min", trustMin);
        }
        if (trustMax != null) {
            query.put("trust_max", trustMax);
        }
        if (StringUtils.isNotBlank(start)) {
            query.put("start", start);
        }
        if (StringUtils.isNotBlank(end)) {
            query.put("end", end);
        }
        query.put("page", safePage);
        query.put("size", safeSize);
        // 排序白名单（Python 端 store.search_facts 同款约束），非法值回落默认
        query.put("sort_by", "trust".equals(sortBy) ? "trust" : "created");
        query.put("order", "asc".equalsIgnoreCase(order) ? "asc" : "desc");

        Map<String, Object> resp = memoryInternalClient.get("/" + agentId + "/facts",
                withDbDir(query, holographDbDir(agentId, userId)));
        Map<String, Object> data = toMap(resp.get("data"));
        List<Map<String, Object>> items = JsonUtils.toStringObjectMapList(data.get("items"));
        List<MemoryFactDTO> list = new ArrayList<>();
        if (items != null) {
            for (Map<String, Object> item : items) {
                list.add(toFactDTO(item));
            }
        }
        return new PageData<>(list, toLong(data.get("total")));
    }

    @Override
    public MemoryFactDTO getFact(String agentId, Long factId, Long userId) {
        if (StringUtils.isBlank(agentId) || factId == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(agentId, userId);
        requireHolographic(agentId, userId);

        Map<String, Object> resp = memoryInternalClient.get(
                resourcePath(agentId, "/facts/" + factId, holographDbDir(agentId, userId)), null);
        return toFactDTO(toMap(resp.get("data")));
    }

    @Override
    public MemoryFactDTO saveFact(MemoryFactDTO dto, Long userId) {
        if (dto == null || StringUtils.isBlank(dto.getAgentId()) || StringUtils.isBlank(dto.getContent())) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(dto.getAgentId(), userId);
        requireHolographic(dto.getAgentId(), userId);

        Map<String, Object> body = new HashMap<>();
        body.put("content", dto.getContent());
        if (StringUtils.isNotBlank(dto.getCategory())) {
            body.put("category", dto.getCategory());
        }
        if (StringUtils.isNotBlank(dto.getTags())) {
            body.put("tags", dto.getTags());
        }
        if (dto.getTrustScore() != null) {
            body.put("trust_score", dto.getTrustScore());
        }

        Map<String, Object> resp = memoryInternalClient.post(
                resourcePath(dto.getAgentId(), "/facts", holographDbDir(dto.getAgentId(), userId)), body);
        return toFactDTO(toMap(resp.get("data")));
    }

    @Override
    public MemoryFactDTO updateFact(Long factId, MemoryFactDTO dto, Long userId) {
        if (dto == null || StringUtils.isBlank(dto.getAgentId()) || factId == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(dto.getAgentId(), userId);
        requireHolographic(dto.getAgentId(), userId);

        Map<String, Object> body = new HashMap<>();
        if (dto.getContent() != null) {
            body.put("content", dto.getContent());
        }
        if (dto.getCategory() != null) {
            body.put("category", dto.getCategory());
        }
        if (dto.getTags() != null) {
            body.put("tags", dto.getTags());
        }
        if (dto.getTrustScore() != null) {
            body.put("trust_score", dto.getTrustScore());
        }

        Map<String, Object> resp = memoryInternalClient.put(
                resourcePath(dto.getAgentId(), "/facts/" + factId, holographDbDir(dto.getAgentId(), userId)), body);
        return toFactDTO(toMap(resp.get("data")));
    }

    @Override
    public void deleteFact(String agentId, Long factId, Long userId) {
        if (StringUtils.isBlank(agentId) || factId == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(agentId, userId);
        requireHolographic(agentId, userId);
        memoryInternalClient.delete(resourcePath(agentId, "/facts/" + factId, holographDbDir(agentId, userId)));
    }

    @Override
    public FeedbackVO feedback(String agentId, Long factId, Boolean helpful, Long userId) {
        if (StringUtils.isBlank(agentId) || factId == null || helpful == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(agentId, userId);
        requireHolographic(agentId, userId);

        Map<String, Object> body = new HashMap<>();
        body.put("helpful", helpful);
        Map<String, Object> resp = memoryInternalClient.post(
                resourcePath(agentId, "/facts/" + factId + "/feedback", holographDbDir(agentId, userId)), body);
        return toFeedbackVO(toMap(resp.get("data")));
    }

    @Override
    public MemoryFactDTO review(String agentId, Long factId, String action, Long userId) {
        if (StringUtils.isBlank(agentId) || factId == null || StringUtils.isBlank(action)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        if (!"approve".equals(action) && !"reject".equals(action)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        checkAgentPermission(agentId, userId);
        requireHolographic(agentId, userId);

        Map<String, Object> body = new HashMap<>();
        body.put("action", action);
        Map<String, Object> resp = memoryInternalClient.post(
                resourcePath(agentId, "/facts/" + factId + "/review", holographDbDir(agentId, userId)), body);
        return toFactDTO(toMap(resp.get("data")));
    }

    /**
     * 解析 Agent 绑定记忆配置的引擎类型（含存在性与权限校验，与 AgentController 同路径）
     */
    private String resolveEngineType(String agentId, Long userId) {
        xiaozhi.modules.agent.vo.AgentInfoVO agent = agentService.getAgentById(agentId, userId);
        String memModelId = agent.getMemModelId();
        if (StringUtils.isBlank(memModelId)) {
            return null;
        }
        return resolveEngineTypeByModelId(memModelId);
    }

    /**
     * 根据记忆模型配置ID解析引擎类型
     */
    private String resolveEngineTypeByModelId(String memModelId) {
        ModelConfigEntity model = modelConfigService.getModelByIdFromCache(memModelId);
        JSONObject configJson = model != null ? model.getConfigJson() : null;
        if (configJson != null) {
            return configJson.getStr("type");
        }
        // 无配置时按模型编码兜底：Memory_mem0ai / Memory_nomem / Memory_mem_report_only
        String lower = memModelId.toLowerCase();
        if (lower.contains("mem0")) {
            return ENGINE_MEM0AI;
        }
        if (lower.contains("nomem")) {
            return "nomem";
        }
        if (lower.contains("mem_report_only")) {
            return "mem_report_only";
        }
        return null;
    }

    /**
     * 解析 holographic 引擎的 db_dir（十路检测 B1 修复：控制台与设备链路双源统一）。
     * 优先取 Agent 记忆模型 configJson.db_dir；无值回落 null（Python 端用全局默认 data/memory/）。
     */
    private String holographDbDir(String agentId, Long userId) {
        try {
            xiaozhi.modules.agent.vo.AgentInfoVO agent = agentService.getAgentById(agentId, userId);
            String memModelId = agent.getMemModelId();
            if (StringUtils.isBlank(memModelId)) {
                return null;
            }
            ModelConfigEntity model = modelConfigService.getModelByIdFromCache(memModelId);
            if (model == null || model.getConfigJson() == null) {
                return null;
            }
            String dbDir = model.getConfigJson().getStr("db_dir");
            return StringUtils.isNotBlank(dbDir) ? dbDir : null;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 给 GET query 追加 db_dir（仅 holographic 自定义目录场景需要；null 时不动）。
     */
    private Map<String, Object> withDbDir(Map<String, Object> query, String dbDir) {
        Map<String, Object> result = query != null ? query : new HashMap<>();
        if (StringUtils.isNotBlank(dbDir)) {
            result.put("db_dir", dbDir);
        }
        return result;
    }

    /** 对资源型路径（/{agentId}/facts/...）拼 db_dir query。 */
    private String resourcePath(String agentId, String tail, String dbDir) {
        String path = "/" + agentId + tail;
        return StringUtils.isNotBlank(dbDir) ? path + "?db_dir=" + java.net.URLEncoder.encode(dbDir, java.nio.charset.StandardCharsets.UTF_8) : path;
    }

    /**
     * 引擎可用性：mem0ai 未配置 API Key 时为 false（apiKeyConfigured 由 ModelConfigServiceImpl 注入），其余已绑引擎默认 true
     */
    private boolean resolveEngineAvailable(String memModelId, String engine) {
        if (ENGINE_MEM0AI.equals(engine)) {
            ModelConfigEntity model = modelConfigService.getModelByIdFromCache(memModelId);
            JSONObject configJson = model != null ? model.getConfigJson() : null;
            if (configJson != null && configJson.getBool("apiKeyConfigured") != null) {
                return configJson.getBool("apiKeyConfigured");
            }
            String apiKey = configJson != null ? configJson.getStr("api_key") : null;
            return StringUtils.isNotBlank(apiKey) && !apiKey.contains("*") && !apiKey.contains("你");
        }
        return engine != null;
    }

    /**
     * 校验当前用户对 Agent 的访问权限（superAdmin 全量，普通用户仅本人 Agent）
     */
    private void checkAgentPermission(String agentId, Long userId) {
        if (!agentService.checkAgentPermission(agentId, userId)) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
    }

    /**
     * 确认 Agent 绑定 holographic 引擎，否则抛友好提示
     */
    private void requireHolographic(String agentId, Long userId) {
        String engine = resolveEngineType(agentId, userId);
        if (ENGINE_MEM_HOLOGRAPHIC.equals(engine)) {
            return;
        }
        if (ENGINE_MEM_LOCAL_SHORT.equals(engine)) {
            throw new RenException("该引擎为压缩档案式记忆，暂不支持条目管理，可切换至 Holographic 引擎");
        }
        if (ENGINE_MEM0AI.equals(engine)) {
            throw new RenException("mem0 平台记忆暂不支持条目编辑（未配置 API Key 或功能建设中），仅可查看配置状态");
        }
        throw new RenException("当前智能体绑定的记忆引擎暂不支持条目管理，请在 Agent 编辑页切换至 Holographic 引擎");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toMap(Object value) {
        if (value instanceof Map) {
            return (Map<String, Object>) value;
        }
        return Collections.emptyMap();
    }

    private MemoryFactDTO toFactDTO(Map<String, Object> map) {
        if (map == null || map.isEmpty()) {
            return null;
        }
        MemoryFactDTO dto = new MemoryFactDTO();
        dto.setFactId(toLong(map.get("fact_id")));
        dto.setContent(str(map.get("content")));
        dto.setCategory(str(map.get("category")));
        dto.setTags(str(map.get("tags")));
        dto.setTrustScore(toDouble(map.get("trust_score")));
        dto.setStatus(str(map.get("status")));
        dto.setAgentId(str(map.get("agent_id")));
        dto.setDeviceId(str(map.get("device_id")));
        dto.setSessionId(str(map.get("session_id")));
        dto.setRetrievalCount(toInteger(map.get("retrieval_count")));
        dto.setHelpfulCount(toInteger(map.get("helpful_count")));
        dto.setCreatedAt(str(map.get("created_at")));
        // 兼容 Python 端出参：PRD 约定 updated_time，SQLite 列名为 updated_at，两者皆取
        dto.setUpdatedTime(str(map.get("updated_time") != null ? map.get("updated_time") : map.get("updated_at")));
        dto.setEntities(JsonUtils.toList(map.get("entities"), String.class));
        dto.setMatchedTerms(JsonUtils.toList(map.get("matched_terms"), String.class));
        return dto;
    }

    private FeedbackVO toFeedbackVO(Map<String, Object> map) {
        FeedbackVO vo = new FeedbackVO();
        vo.setFactId(toLong(map.get("fact_id")));
        vo.setOldTrust(toDouble(map.get("old_trust")));
        vo.setNewTrust(toDouble(map.get("new_trust")));
        vo.setHelpfulCount(toInteger(map.get("helpful_count")));
        return vo;
    }

    private String str(Object value) {
        return value == null ? null : value.toString();
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(value.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Integer toInteger(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return Integer.parseInt(value.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Double toDouble(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        try {
            return Double.parseDouble(value.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
