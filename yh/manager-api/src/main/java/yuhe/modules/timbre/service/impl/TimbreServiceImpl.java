package yuhe.modules.timbre.service.impl;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import cn.hutool.core.collection.CollectionUtil;
import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.redis.RedisKeys;
import yuhe.common.redis.RedisUtils;
import yuhe.common.service.impl.BaseServiceImpl;
import yuhe.common.utils.ConvertUtils;
import yuhe.common.utils.MessageUtils;
import yuhe.modules.agent.dao.AgentDao;
import yuhe.modules.agent.entity.AgentEntity;
import yuhe.modules.model.dto.VoiceDTO;
import yuhe.modules.model.service.ModelConfigService;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.service.SysParamsService;
import yuhe.modules.timbre.dao.TimbreDao;
import yuhe.modules.timbre.dto.TimbreDataDTO;
import yuhe.modules.timbre.dto.TimbrePageDTO;
import yuhe.modules.timbre.entity.TimbreEntity;
import yuhe.modules.timbre.service.TimbreService;
import yuhe.modules.timbre.vo.TimbreDetailsVO;
import yuhe.modules.voiceclone.dao.VoiceCloneDao;
import yuhe.modules.voiceclone.entity.VoiceCloneEntity;

/**
 * 音色的业务层的实现
 * 
 * @author zjy
 * @since 2025-3-21
 */
@AllArgsConstructor
@Service
public class TimbreServiceImpl extends BaseServiceImpl<TimbreDao, TimbreEntity> implements TimbreService {

    private static final Pattern LANGUAGE_SEPARATOR = Pattern.compile("[、；;,，]");

    /** 探测请求超时（秒）：46 音色 5 并发，单请求上限给足 */
    private static final int PROBE_TIMEOUT_SECONDS = 180;

    private static final String DEFAULT_HTTP_PORT = "8003";

    private static final HttpClient PROBE_HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final TimbreDao timbreDao;
    private final VoiceCloneDao voiceCloneDao;
    private final RedisUtils redisUtils;
    private final ModelConfigService modelConfigService;
    private final SysParamsService sysParamsService;
    private final AgentDao agentDao;

    @Override
    public PageData<TimbreDetailsVO> page(TimbrePageDTO dto) {
        Map<String, Object> params = new HashMap<String, Object>();
        params.put(Constant.PAGE, dto.getPage());
        params.put(Constant.LIMIT, dto.getLimit());
        IPage<TimbreEntity> page = baseDao.selectPage(
                getPage(params, null, true),
                // 定义查询条件
                new QueryWrapper<TimbreEntity>()
                        // 必须按照ttsID查找
                        .eq("tts_model_id", dto.getTtsModelId())
                        // 如果有音色名字，按照音色名模糊查找
                        .like(StringUtils.isNotBlank(dto.getName()), "name", dto.getName()));

        return getPageData(page, TimbreDetailsVO.class);
    }

    @Override
    public TimbreDetailsVO get(String timbreId) {
        if (StringUtils.isBlank(timbreId)) {
            return null;
        }

        // 先从Redis获取缓存
        String key = RedisKeys.getTimbreDetailsKey(timbreId);
        TimbreDetailsVO cachedDetails = (TimbreDetailsVO) redisUtils.get(key);
        if (cachedDetails != null) {
            return cachedDetails;
        }

        // 如果缓存中没有，则从数据库获取
        TimbreEntity entity = baseDao.selectById(timbreId);
        if (entity == null) {
            return null;
        }

        // 转换为VO对象
        TimbreDetailsVO details = ConvertUtils.sourceToTarget(entity, TimbreDetailsVO.class);

        // 存入Redis缓存
        if (details != null) {
            redisUtils.set(key, details);
        }

        return details;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void save(TimbreDataDTO dto) {
        isTtsModelId(dto.getTtsModelId());
        if (dto.getSort() == null) {
            dto.setSort(0L);
        }
        TimbreEntity timbreEntity = ConvertUtils.sourceToTarget(dto, TimbreEntity.class);
        baseDao.insert(timbreEntity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(String timbreId, TimbreDataDTO dto) {
        isTtsModelId(dto.getTtsModelId());
        TimbreEntity timbreEntity = ConvertUtils.sourceToTarget(dto, TimbreEntity.class);
        timbreEntity.setId(timbreId);
        baseDao.updateById(timbreEntity);
        // 删除缓存
        redisUtils.delete(RedisKeys.getTimbreDetailsKey(timbreId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(String[] ids) {
        baseDao.deleteByIds(Arrays.asList(ids));
    }

    @Override
    public List<VoiceDTO> getVoiceNames(String ttsModelId, String voiceName) {
        QueryWrapper<TimbreEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("tts_model_id", StringUtils.isBlank(ttsModelId) ? "" : ttsModelId);
        if (StringUtils.isNotBlank(voiceName)) {
            queryWrapper.like("name", voiceName);
        }
        List<TimbreEntity> timbreEntities = Optional.ofNullable(timbreDao.selectList(queryWrapper)).orElseGet(ArrayList::new);
        List<VoiceDTO> voiceDTOs = timbreEntities.stream()
                .map(entity -> {
                    VoiceDTO dto = new VoiceDTO(entity.getId(), entity.getName());
                    dto.setVoiceDemo(entity.getVoiceDemo());
                    dto.setLanguages(entity.getLanguages()); // 设置语言类型
                    dto.setIsClone(false); // 设置为普通音色
                    dto.setTtsVoice(entity.getTtsVoice()); // 平台音色ID（试听合成用）
                    dto.setVoiceInstruction(entity.getVoiceInstruction()); // 音色级语气指令（编辑回显）
                    dto.setDynamicInstruction(entity.getDynamicInstruction()); // 动态指令开关
                    dto.setInstructionLlmId(entity.getInstructionLlmId()); // 动态指令生成 LLM
                    return dto;
                })
                .collect(Collectors.toList());

        // 获取当前登录用户ID
        Long currentUserId = SecurityUser.getUser().getId();
        if (currentUserId != null) {
            // 查询用户的所有克隆音色记录
            List<VoiceDTO> cloneEntities = voiceCloneDao.getTrainSuccess(ttsModelId, currentUserId);
            for (VoiceDTO entity : cloneEntities) {
                // 只添加训练成功的克隆音色，且模型ID匹配
                VoiceDTO voiceDTO = new VoiceDTO();
                voiceDTO.setId(entity.getId());
                voiceDTO.setName(MessageUtils.getMessage(ErrorCode.VOICE_CLONE_PREFIX) + entity.getName());
                // 保留从数据库查询到的voiceDemo字段
                voiceDTO.setVoiceDemo(entity.getVoiceDemo());
                voiceDTO.setLanguages(entity.getLanguages());
                voiceDTO.setIsClone(true); // 设置为克隆音色
                redisUtils.set(RedisKeys.getTimbreNameById(voiceDTO.getId()), voiceDTO.getName(),
                        RedisUtils.NOT_EXPIRE);
                voiceDTOs.add(0, voiceDTO);
            }
        }

        return CollectionUtil.isEmpty(voiceDTOs) ? null : voiceDTOs;
    }

    @Override
    public String getDefaultLanguageById(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }

        TimbreEntity timbre = timbreDao.selectById(id);
        if (timbre != null) {
            return firstNonBlankLanguage(timbre.getLanguages());
        }

        VoiceCloneEntity voiceClone = voiceCloneDao.selectById(id);
        return voiceClone == null ? null : firstNonBlankLanguage(voiceClone.getLanguages());
    }

    private String firstNonBlankLanguage(String languages) {
        if (StringUtils.isBlank(languages)) {
            return null;
        }
        return LANGUAGE_SEPARATOR.splitAsStream(languages)
                .map(StringUtils::trimToNull)
                .filter(Objects::nonNull)
                .findFirst()
                .orElse(null);
    }

    /**
     * 处理是不是tts模型的id
     */
    private void isTtsModelId(String ttsModelId) {
        // 等模型配置那边写好调用方法判断
    }

    @Override
    public String getTimbreNameById(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }

        String cachedName = (String) redisUtils.get(RedisKeys.getTimbreNameById(id));

        if (StringUtils.isNotBlank(cachedName)) {
            return cachedName;
        }

        TimbreEntity entity = timbreDao.selectById(id);
        if (entity != null) {
            String name = entity.getName();
            if (StringUtils.isNotBlank(name)) {
                redisUtils.set(RedisKeys.getTimbreNameById(id), name);
            }
            return name;
        } else {
            VoiceCloneEntity cloneEntity = voiceCloneDao.selectById(id);
            if (cloneEntity != null) {
                String name = MessageUtils.getMessage(ErrorCode.VOICE_CLONE_PREFIX) + cloneEntity.getName();
                redisUtils.set(RedisKeys.getTimbreNameById(id), name);
                return name;
            }
        }

        return null;
    }

    @Override
    public VoiceDTO getByVoiceCode(String ttsModelId, String voiceCode) {
        if (StringUtils.isBlank(voiceCode)) {
            return null;
        }
        QueryWrapper<TimbreEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("tts_model_id", ttsModelId);
        queryWrapper.eq("tts_voice", voiceCode);
        List<TimbreEntity> list = timbreDao.selectList(queryWrapper);
        if (list.isEmpty()) {
            return null;
        }
        TimbreEntity entity = list.get(0);
        VoiceDTO dto = new VoiceDTO(entity.getId(), entity.getName());
        dto.setVoiceDemo(entity.getVoiceDemo());
        dto.setIsClone(false); // 设置为普通音色
        dto.setTtsVoice(entity.getTtsVoice());
        dto.setVoiceInstruction(entity.getVoiceInstruction());
        dto.setDynamicInstruction(entity.getDynamicInstruction());
        dto.setInstructionLlmId(entity.getInstructionLlmId());
        return dto;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> probeAndSync(String ttsModelId) {
        if (StringUtils.isBlank(ttsModelId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }

        // 1. 模型原始配置（含凭据，仅服务间转发用）
        String rawConfig = modelConfigService.getRawConfigJson(ttsModelId);
        if (rawConfig == null || rawConfig.isBlank()) {
            RenException exception = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            exception.setMsg("模型不存在或未配置");
            throw exception;
        }
        String providerType;
        try {
            providerType = JSONUtil.parseObj(rawConfig).getStr("type", "");
        } catch (Exception e) {
            throw new RenException("模型配置解析失败");
        }
        if (!"aliyun_multimodal".equals(providerType)) {
            throw new RenException("当前仅支持百炼多模态TTS(aliyun_multimodal)的音色探测");
        }

        // 2. 现有音色（系统+可能的历史遗留），供 Python 合并候选（DB 现有 + 内置 3.1 池）
        List<TimbreEntity> existing = Optional.ofNullable(timbreDao.selectList(
                new QueryWrapper<TimbreEntity>().eq("tts_model_id", ttsModelId))).orElseGet(ArrayList::new);
        Map<String, TimbreEntity> existingByVoice = existing.stream()
                .filter(e -> StringUtils.isNotBlank(e.getTtsVoice()))
                .collect(Collectors.toMap(TimbreEntity::getTtsVoice, e -> e, (a, b) -> a));

        // 3. 调 yuhe-server 探测 API
        JSONObject reqBody = new JSONObject();
        reqBody.set("config_json", JSONUtil.parseObj(rawConfig));
        JSONArray voicesArr = new JSONArray();
        for (TimbreEntity e : existing) {
            if (StringUtils.isNotBlank(e.getTtsVoice())) {
                JSONObject v = new JSONObject();
                v.set("id", e.getId());
                v.set("tts_voice", e.getTtsVoice());
                v.set("name", e.getName());
                voicesArr.add(v);
            }
        }
        reqBody.set("voices", voicesArr);

        JSONArray probeResults = callProbeApi(reqBody);

        // 4. 结果分类
        List<JSONObject> validItems = new ArrayList<>();
        List<JSONObject> invalidItems = new ArrayList<>();
        for (Object o : probeResults) {
            JSONObject item = (JSONObject) o;
            if (item.getBool("valid", false)) {
                validItems.add(item);
            } else {
                invalidItems.add(item);
            }
        }
        if (validItems.isEmpty()) {
            throw new RenException("探测结果全部失效（引擎可能未发布或配置错误），已放弃同步以保护现有音色");
        }

        Set<String> validVoices = validItems.stream()
                .map(i -> i.getStr("tts_voice")).collect(Collectors.toSet());

        // 5. 删除失效音色（用户自建 reference_audio 非空的不动；仅删系统静态音色）
        List<String> removedNames = new ArrayList<>();
        List<String> removedIds = new ArrayList<>();
        for (TimbreEntity e : existing) {
            if (validVoices.contains(e.getTtsVoice())) {
                continue;
            }
            if (StringUtils.isNotBlank(e.getReferenceAudio())) {
                continue; // 用户自建/克隆引用，不动
            }
            removedIds.add(e.getId());
            removedNames.add(e.getName() + "(" + e.getTtsVoice() + ")");
        }
        if (!removedIds.isEmpty()) {
            baseDao.deleteByIds(removedIds);
        }

        // 6. 新增不在 DB 的有效音色（id 规则：{modelId}_{4位序号}，避开已占用）
        List<String> addedNames = new ArrayList<>();
        Set<String> usedIdSuffixes = existing.stream().map(TimbreEntity::getId)
                .filter(id -> id != null && id.startsWith(ttsModelId + "_"))
                .map(id -> id.substring(ttsModelId.length() + 1))
                .collect(Collectors.toSet());
        int seq = 1;
        for (JSONObject item : validItems) {
            String voice = item.getStr("tts_voice");
            if (existingByVoice.containsKey(voice)) {
                continue;
            }
            TimbreEntity entity = new TimbreEntity();
            String nextId;
            do {
                nextId = String.format("%s_%04d", ttsModelId, seq++);
            } while (usedIdSuffixes.contains(String.format("%04d", seq - 1)));
            entity.setId(nextId);
            entity.setTtsModelId(ttsModelId);
            entity.setName(item.getStr("name", voice));
            entity.setTtsVoice(voice);
            entity.setLanguages(guessLanguage(voice));
            entity.setSort(0L);
            Date now = new Date();
            entity.setCreateDate(now);
            entity.setUpdateDate(now);
            Long uid = SecurityUser.getUserId();
            entity.setCreator(uid);
            entity.setUpdater(uid);
            baseDao.insert(entity);
            addedNames.add(entity.getName() + "(" + voice + ")");
        }

        // 7. 失效音色的智能体引用迁移：agent.tts_voice_id → 该模型首个有效音色
        List<String> migratedAgents = new ArrayList<>();
        if (!removedIds.isEmpty()) {
            List<AgentEntity> agents = agentDao.selectList(new QueryWrapper<AgentEntity>()
                    .eq("tts_model_id", ttsModelId).in("tts_voice_id", removedIds));
            if (!agents.isEmpty() && !validItems.isEmpty()) {
                // 迁移目标：优先 DB 中保留的（existing∩valid）任一，否则新插入的第一个
                String fallbackVoiceId = null;
                for (TimbreEntity e : existing) {
                    if (validVoices.contains(e.getTtsVoice())) {
                        fallbackVoiceId = e.getId();
                        break;
                    }
                }
                if (fallbackVoiceId == null) {
                    // 全删全换场景：从插入结果回查
                    TimbreEntity first = timbreDao.selectOne(new QueryWrapper<TimbreEntity>()
                            .eq("tts_model_id", ttsModelId).eq("tts_voice", validItems.get(0).getStr("tts_voice")));
                    fallbackVoiceId = first != null ? first.getId() : null;
                }
                if (fallbackVoiceId != null) {
                    for (AgentEntity agent : agents) {
                        agent.setTtsVoiceId(fallbackVoiceId);
                        agentDao.updateById(agent);
                        redisUtils.delete(RedisKeys.getTimbreDetailsKey(agent.getTtsVoiceId()));
                        migratedAgents.add(agent.getAgentName() + "#" + agent.getId());
                    }
                }
            }
        }

        // 8. 清缓存（音色详情 + 名称 + 模型配置下发链路）
        for (TimbreEntity e : existing) {
            redisUtils.delete(RedisKeys.getTimbreDetailsKey(e.getId()));
            redisUtils.delete(RedisKeys.getTimbreNameById(e.getId()));
        }
        redisUtils.delete("model:data:" + ttsModelId);
        redisUtils.delete("model:name:" + ttsModelId);
        redisUtils.delete("server:config");

        // 9. 探测报告
        Map<String, Object> report = new HashMap<>();
        report.put("probedTotal", probeResults.size());
        report.put("validCount", validItems.size());
        report.put("invalidCount", invalidItems.size());
        report.put("added", addedNames);
        report.put("removed", removedNames);
        report.put("migratedAgents", migratedAgents);
        List<Map<String, String>> invalidDetail = new ArrayList<>();
        for (JSONObject i : invalidItems) {
            Map<String, String> d = new HashMap<>();
            d.put("tts_voice", i.getStr("tts_voice"));
            d.put("name", i.getStr("name", ""));
            d.put("reason", i.getStr("reason", ""));
            invalidDetail.add(d);
        }
        report.put("invalidDetail", invalidDetail);
        return report;
    }

    /** 调 yuhe-server /api/tts/voice-probe（服务间 server.secret 鉴权），返回探测结果数组 */
    private JSONArray callProbeApi(JSONObject reqBody) {
        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, false);
        if (secret == null || secret.trim().isEmpty()) {
            throw new RenException("服务密钥未配置(server.secret)");
        }
        String port = sysParamsService.getValue("server.http_port", true);
        if (port == null || port.trim().isEmpty() || "null".equals(port)) {
            port = DEFAULT_HTTP_PORT;
        }
        String url = "http://127.0.0.1:" + port.trim() + "/api/tts/voice-probe";
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", "Bearer " + secret.trim())
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(PROBE_TIMEOUT_SECONDS))
                    .POST(HttpRequest.BodyPublishers.ofString(reqBody.toString(), StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = PROBE_HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 401) {
                throw new RenException("服务密钥不一致，请检查 server.secret");
            }
            if (response.statusCode() != 200) {
                String msg = null;
                try {
                    msg = JSONUtil.parseObj(response.body()).getStr("msg");
                } catch (Exception ignore) {
                }
                throw new RenException(msg != null ? msg : "探测服务不可用（状态码 " + response.statusCode() + "）");
            }
            JSONObject resp = JSONUtil.parseObj(response.body());
            if (resp.getInt("code", -1) != 0) {
                throw new RenException(resp.getStr("msg", "探测失败"));
            }
            JSONArray data = resp.getJSONArray("data");
            if (data == null || data.isEmpty()) {
                throw new RenException("探测返回空结果");
            }
            return data;
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException("探测服务超时或不可用: " + e.getMessage());
        }
    }

    /** 按 voice 编码粗略推断语言标签（3.1 音色：英文系列仅英文，其余普通话） */
    private String guessLanguage(String voice) {
        if (voice == null) {
            return "普通话";
        }
        String v = voice.toLowerCase();
        boolean englishSeries = v.startsWith("emily") || v.startsWith("luna") || v.startsWith("eric")
                || v.startsWith("luca") || v.startsWith("abby") || v.startsWith("annie")
                || v.startsWith("ava") || v.startsWith("beth") || v.startsWith("betty")
                || v.startsWith("cally") || v.startsWith("cindy") || v.startsWith("donna")
                || v.startsWith("andy") || v.startsWith("brian") || v.startsWith("david")
                || v.startsWith("loongbella");
        boolean multilingual = v.startsWith("longanlingxin") || v.startsWith("longanhuan")
                || v.startsWith("longanfengyue") || v.startsWith("xunanchuan");
        if (englishSeries) {
            return "英语";
        }
        if (multilingual) {
            return "普通话、方言、多语种";
        }
        return "普通话";
    }
}
