package yuhe.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.utils.AESUtils;
import yuhe.common.utils.DateUtils;
import yuhe.common.utils.JsonUtils;
import yuhe.common.utils.SensitiveDataUtils;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.dao.SysParamsDao;
import yuhe.modules.sys.dao.SysUserCustomModelDao;
import yuhe.modules.sys.dao.SysUserCustomVoiceDao;
import yuhe.modules.sys.entity.SysUserCustomModelEntity;
import yuhe.modules.sys.entity.SysUserCustomVoiceEntity;
import yuhe.modules.sys.service.UserResourceService;
import yuhe.modules.timbre.dao.TimbreDao;
import yuhe.modules.timbre.entity.TimbreEntity;

/**
 * 用户端资源实现（console-v2 顾客端 SPEC §6）：
 * 平台音色 + 本人自定义模型/音色；api_key AES 加密落库，任何响应不回明文/密文（仅掩码）。
 */
@Service
public class UserResourceServiceImpl implements UserResourceService {

    /** API Key AES 密钥：优先 sys_params（key=user.apiKeyCipherKey），缺省用固定兜底密钥 */
    private static final String DEFAULT_AES_KEY = "yuhe-user-apikey-2026";
    private static final String PARAM_API_KEY = "user.apiKeyCipherKey";

    private final SysUserCustomModelDao modelDao;
    private final SysUserCustomVoiceDao voiceDao;
    private final TimbreDao timbreDao;
    private final SysParamsDao sysParamsDao;

    public UserResourceServiceImpl(SysUserCustomModelDao modelDao, SysUserCustomVoiceDao voiceDao,
            TimbreDao timbreDao, SysParamsDao sysParamsDao) {
        this.modelDao = modelDao;
        this.voiceDao = voiceDao;
        this.timbreDao = timbreDao;
        this.sysParamsDao = sysParamsDao;
    }

    // ==================== 资源聚合 ====================

    @Override
    public Map<String, Object> myResources() {
        Long userId = SecurityUser.getUserId();
        Map<String, Object> data = new LinkedHashMap<>();
        List<Map<String, Object>> ttsVoices = new ArrayList<>();
        // 平台音色（全部）
        LambdaQueryWrapper<TimbreEntity> tw = new LambdaQueryWrapper<TimbreEntity>()
                .orderByAsc(TimbreEntity::getSort).orderByAsc(TimbreEntity::getId);
        for (TimbreEntity t : timbreDao.selectList(tw)) {
            Map<String, Object> v = new LinkedHashMap<>();
            v.put("id", t.getId());
            v.put("name", t.getName());
            v.put("ttsModelId", t.getTtsModelId());
            v.put("ttsVoice", t.getTtsVoice());
            v.put("languages", t.getLanguages());
            v.put("remark", t.getRemark());
            ttsVoices.add(v);
        }
        // 本人审核通过的自定义音色（附加进列表）
        if (userId != null) {
            LambdaQueryWrapper<SysUserCustomVoiceEntity> vw = new LambdaQueryWrapper<SysUserCustomVoiceEntity>()
                    .eq(SysUserCustomVoiceEntity::getUserId, userId)
                    .eq(SysUserCustomVoiceEntity::getAuditStatus, 1);
            for (SysUserCustomVoiceEntity v : voiceDao.selectList(vw)) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("id", v.getId());
                m.put("name", v.getName());
                m.put("ttsModelId", v.getTtsModelId());
                m.put("ttsVoice", v.getTtsVoice());
                m.put("languages", v.getLanguages());
                m.put("remark", v.getRemark());
                ttsVoices.add(m);
            }
        }
        data.put("ttsVoices", ttsVoices);
        return data;
    }

    // ==================== 自定义模型 ====================

    @Override
    public PageData<Map<String, Object>> customModelPage(Map<String, Object> params) {
        Long userId = requireUserId();
        long page = parseLong(params, Constant.PAGE, 1L);
        long limit = parseLong(params, Constant.LIMIT, 10L);
        LambdaQueryWrapper<SysUserCustomModelEntity> qw = new LambdaQueryWrapper<SysUserCustomModelEntity>()
                .eq(SysUserCustomModelEntity::getUserId, userId)
                .orderByDesc(SysUserCustomModelEntity::getCreateDate)
                .orderByDesc(SysUserCustomModelEntity::getId);
        IPage<SysUserCustomModelEntity> p = modelDao.selectPage(new Page<>(page, limit), qw);
        List<Map<String, Object>> list = p.getRecords().stream().map(this::toModelMap).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> customModelCreate(Map<String, Object> body) {
        Long userId = requireUserId();
        String modelName = str(body, "modelName");
        if (StringUtils.isBlank(modelName)) {
            throw new RenException("模型名称不能为空");
        }
        checkDuplicateModel(userId, modelName, null);
        SysUserCustomModelEntity e = new SysUserCustomModelEntity();
        e.setId(UUID.randomUUID().toString().replace("-", ""));
        e.setUserId(userId);
        e.setModelType(StringUtils.defaultIfBlank(str(body, "modelType"), "LLM"));
        e.setModelName(modelName.trim());
        e.setProviderCode(str(body, "providerCode"));
        e.setBaseUrl(str(body, "baseUrl"));
        String apiKey = str(body, "apiKey");
        if (StringUtils.isNotBlank(apiKey)) {
            e.setApiKeyCipher(encryptKey(apiKey.trim()));
        }
        e.setConfigJson(null);
        e.setAuditStatus(0);
        e.setStatus(1);
        e.setQuotaLimit(null);
        e.setUsedCount(0L);
        e.setRemark(str(body, "remark"));
        e.setSort(0);
        e.setCreator(userId);
        e.setCreateDate(new Date());
        modelDao.insert(e);
        return toModelMap(e);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> customModelUpdate(String id, Map<String, Object> body) {
        Long userId = requireUserId();
        SysUserCustomModelEntity e = requireOwnedModel(userId, id);
        String modelName = str(body, "modelName");
        if (StringUtils.isNotBlank(modelName)) {
            checkDuplicateModel(userId, modelName.trim(), id);
            e.setModelName(modelName.trim());
        }
        e.setModelType(StringUtils.defaultIfBlank(str(body, "modelType"), e.getModelType()));
        if (body.containsKey("providerCode")) {
            e.setProviderCode(str(body, "providerCode"));
        }
        if (body.containsKey("baseUrl")) {
            e.setBaseUrl(str(body, "baseUrl"));
        }
        // 契约：编辑时 apiKey 留空 = 不修改
        String apiKey = str(body, "apiKey");
        if (StringUtils.isNotBlank(apiKey)) {
            e.setApiKeyCipher(encryptKey(apiKey.trim()));
        }
        if (body.containsKey("remark")) {
            e.setRemark(str(body, "remark"));
        }
        e.setUpdater(userId);
        e.setUpdateDate(new Date());
        modelDao.updateById(e);
        return toModelMap(e);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void customModelDelete(String id) {
        Long userId = requireUserId();
        requireOwnedModel(userId, id);
        modelDao.deleteById(id);
    }

    @Override
    public Map<String, Object> customModelHealth(String id) {
        Long userId = requireUserId();
        SysUserCustomModelEntity e = requireOwnedModel(userId, id);
        Map<String, Object> data = new LinkedHashMap<>();
        String baseUrl = e.getBaseUrl();
        if (StringUtils.isBlank(baseUrl)) {
            data.put("status", 0);
            data.put("latencyMs", 0);
            data.put("msg", "未配置 Base URL");
            return data;
        }
        long start = System.currentTimeMillis();
        int latencyMs;
        try (HttpResponse resp = HttpRequest.get(baseUrl).timeout(8000).execute()) {
            latencyMs = (int) (System.currentTimeMillis() - start);
            int code = resp.getStatus();
            data.put("status", code < 500 ? 1 : 0);
            data.put("latencyMs", latencyMs);
            data.put("msg", "HTTP " + code);
        } catch (Exception ex) {
            latencyMs = (int) (System.currentTimeMillis() - start);
            data.put("status", 0);
            data.put("latencyMs", latencyMs);
            data.put("msg", "连接失败：" + ex.getMessage());
        }
        return data;
    }

    // ==================== 自定义音色 ====================

    @Override
    public PageData<Map<String, Object>> customVoicePage(Map<String, Object> params) {
        Long userId = requireUserId();
        long page = parseLong(params, Constant.PAGE, 1L);
        long limit = parseLong(params, Constant.LIMIT, 10L);
        LambdaQueryWrapper<SysUserCustomVoiceEntity> qw = new LambdaQueryWrapper<SysUserCustomVoiceEntity>()
                .eq(SysUserCustomVoiceEntity::getUserId, userId)
                .orderByDesc(SysUserCustomVoiceEntity::getCreateDate)
                .orderByDesc(SysUserCustomVoiceEntity::getId);
        IPage<SysUserCustomVoiceEntity> p = voiceDao.selectPage(new Page<>(page, limit), qw);
        List<Map<String, Object>> list = p.getRecords().stream().map(this::toVoiceMap).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> customVoiceCreate(Map<String, Object> body) {
        Long userId = requireUserId();
        String name = str(body, "name");
        if (StringUtils.isBlank(name)) {
            throw new RenException("音色名称不能为空");
        }
        SysUserCustomVoiceEntity e = new SysUserCustomVoiceEntity();
        e.setId(UUID.randomUUID().toString().replace("-", ""));
        e.setUserId(userId);
        e.setName(name.trim());
        e.setTtsModelId(str(body, "ttsModelId"));
        e.setTtsVoice(str(body, "voiceCode"));
        e.setLanguages(str(body, "language"));
        e.setReferenceAudio(str(body, "referenceAudio"));
        e.setReferenceText(str(body, "referenceText"));
        e.setAuditStatus(0);
        e.setStatus(1);
        e.setRemark(str(body, "remark"));
        e.setSort(0);
        e.setCreator(userId);
        e.setCreateDate(new Date());
        voiceDao.insert(e);
        return toVoiceMap(e);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> customVoiceUpdate(String id, Map<String, Object> body) {
        Long userId = requireUserId();
        SysUserCustomVoiceEntity e = requireOwnedVoice(userId, id);
        if (StringUtils.isNotBlank(str(body, "name"))) {
            e.setName(str(body, "name").trim());
        }
        if (body.containsKey("ttsModelId")) {
            e.setTtsModelId(str(body, "ttsModelId"));
        }
        if (body.containsKey("voiceCode")) {
            e.setTtsVoice(str(body, "voiceCode"));
        }
        if (body.containsKey("language")) {
            e.setLanguages(str(body, "language"));
        }
        if (body.containsKey("referenceAudio")) {
            e.setReferenceAudio(str(body, "referenceAudio"));
        }
        if (body.containsKey("referenceText")) {
            e.setReferenceText(str(body, "referenceText"));
        }
        if (body.containsKey("remark")) {
            e.setRemark(str(body, "remark"));
        }
        e.setUpdater(userId);
        e.setUpdateDate(new Date());
        voiceDao.updateById(e);
        return toVoiceMap(e);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void customVoiceDelete(String id) {
        Long userId = requireUserId();
        requireOwnedVoice(userId, id);
        voiceDao.deleteById(id);
    }

    // ==================== 私有工具 ====================

    private Long requireUserId() {
        Long userId = SecurityUser.getUserId();
        if (userId == null) {
            throw new RenException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    private SysUserCustomModelEntity requireOwnedModel(Long userId, String id) {
        SysUserCustomModelEntity e = modelDao.selectById(id);
        if (e == null || !e.getUserId().equals(userId)) {
            throw new RenException(ErrorCode.ADMIN_CUSTOM_NOT_EXIST);
        }
        return e;
    }

    private SysUserCustomVoiceEntity requireOwnedVoice(Long userId, String id) {
        SysUserCustomVoiceEntity e = voiceDao.selectById(id);
        if (e == null || !e.getUserId().equals(userId)) {
            throw new RenException(ErrorCode.ADMIN_CUSTOM_NOT_EXIST);
        }
        return e;
    }

    private void checkDuplicateModel(Long userId, String modelName, String excludeId) {
        LambdaQueryWrapper<SysUserCustomModelEntity> qw = new LambdaQueryWrapper<SysUserCustomModelEntity>()
                .eq(SysUserCustomModelEntity::getUserId, userId)
                .eq(SysUserCustomModelEntity::getModelName, modelName);
        if (excludeId != null) {
            qw.ne(SysUserCustomModelEntity::getId, excludeId);
        }
        if (modelDao.selectCount(qw) > 0) {
            // 前端提示"同类型下已存在同名模型"，10234 语义复用
            throw new RenException(ErrorCode.ADMIN_ROLE_HAS_USERS);
        }
    }

    private Map<String, Object> toModelMap(SysUserCustomModelEntity e) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", e.getId());
        m.put("modelType", e.getModelType());
        m.put("modelName", e.getModelName());
        m.put("providerCode", e.getProviderCode());
        m.put("baseUrl", e.getBaseUrl());
        m.put("apiKeyMask", SensitiveDataUtils.maskMiddle(e.getApiKeyCipher()));
        m.put("auditStatus", e.getAuditStatus());
        m.put("auditRemark", e.getAuditRemark());
        m.put("usedCount", e.getUsedCount());
        m.put("quotaLimit", e.getQuotaLimit());
        m.put("status", e.getStatus());
        m.put("remark", e.getRemark());
        m.put("createDate", e.getCreateDate() == null ? null : DateUtils.format(e.getCreateDate(), DateUtils.DATE_TIME_PATTERN));
        return m;
    }

    private Map<String, Object> toVoiceMap(SysUserCustomVoiceEntity e) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", e.getId());
        m.put("name", e.getName());
        m.put("ttsModelId", e.getTtsModelId());
        m.put("voiceCode", e.getTtsVoice());
        m.put("language", e.getLanguages());
        m.put("referenceAudio", e.getReferenceAudio());
        m.put("referenceText", e.getReferenceText());
        m.put("auditStatus", e.getAuditStatus());
        m.put("auditRemark", e.getAuditRemark());
        m.put("status", e.getStatus());
        m.put("remark", e.getRemark());
        m.put("createDate", e.getCreateDate() == null ? null : DateUtils.format(e.getCreateDate(), DateUtils.DATE_TIME_PATTERN));
        return m;
    }

    private String str(Map<String, Object> body, String key) {
        Object v = body == null ? null : body.get(key);
        return v == null ? null : String.valueOf(v);
    }

    private long parseLong(Map<String, Object> params, String key, long def) {
        Object v = params == null ? null : params.get(key);
        if (v == null || StringUtils.isBlank(String.valueOf(v))) {
            return def;
        }
        try {
            return Long.parseLong(String.valueOf(v));
        } catch (NumberFormatException e) {
            return def;
        }
    }

    private String getAesKey() {
        try {
            String configured = sysParamsDao.getValueByCode(PARAM_API_KEY);
            if (StringUtils.isNotBlank(configured)) {
                return configured;
            }
        } catch (Exception ignored) {
            // 配置读取失败回落兜底密钥
        }
        return DEFAULT_AES_KEY;
    }

    private String encryptKey(String plain) {
        return AESUtils.encrypt(getAesKey(), plain);
    }
}
