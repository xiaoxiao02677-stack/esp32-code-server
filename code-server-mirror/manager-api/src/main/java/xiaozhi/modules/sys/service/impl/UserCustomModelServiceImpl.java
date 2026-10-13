package xiaozhi.modules.sys.service.impl;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.AesGcmUtils;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.dao.SysUserCustomModelDao;
import xiaozhi.modules.sys.entity.SysUserCustomModelEntity;
import xiaozhi.modules.sys.service.AuditService;
import xiaozhi.modules.sys.service.UserCustomModelService;

/**
 * 用户自定义模型实现（AES-256-GCM 密钥加密 + 审核 + 配额 + 健康检查）
 */
@Service
@AllArgsConstructor
public class UserCustomModelServiceImpl implements UserCustomModelService {

    private final SysUserCustomModelDao sysUserCustomModelDao;
    private final AuditService auditService;

    @Value("${security.user-module.api-key-secret:xzh-user-module-aes-key-2026-CHANGE-ME}")
    private String apiKeySecret;

    @Override
    public List<Map<String, Object>> myList(Long userId, String modelType, Integer auditStatus) {
        LambdaQueryWrapper<SysUserCustomModelEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserCustomModelEntity::getUserId, userId);
        wrapper.eq(StringUtils.isNotBlank(modelType), SysUserCustomModelEntity::getModelType,
                modelType == null ? null : modelType.toUpperCase());
        wrapper.eq(auditStatus != null, SysUserCustomModelEntity::getAuditStatus, auditStatus);
        wrapper.orderByDesc(SysUserCustomModelEntity::getCreateDate);

        List<SysUserCustomModelEntity> list = sysUserCustomModelDao.selectList(wrapper);
        List<Map<String, Object>> result = new ArrayList<>();
        for (SysUserCustomModelEntity e : list) {
            result.add(toVo(e, true));
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(Long userId, Map<String, Object> body) {
        String modelType = str(body, "modelType");
        String modelName = str(body, "modelName");
        String apiKey = str(body, "apiKey");

        if (StringUtils.isBlank(modelType) || StringUtils.isBlank(modelName)) {
            throw new RenException(ErrorCode.NOT_NULL);
        }
        modelType = modelType.toUpperCase();

        // 同型同名查重（10234）
        LambdaQueryWrapper<SysUserCustomModelEntity> dupWrapper = new LambdaQueryWrapper<>();
        dupWrapper.eq(SysUserCustomModelEntity::getUserId, userId);
        dupWrapper.eq(SysUserCustomModelEntity::getModelType, modelType);
        dupWrapper.eq(SysUserCustomModelEntity::getModelName, modelName);
        if (sysUserCustomModelDao.selectCount(dupWrapper) > 0) {
            throw new RenException(ErrorCode.CUSTOM_MODEL_DUPLICATE);
        }

        SysUserCustomModelEntity entity = new SysUserCustomModelEntity();
        entity.setId(UUID.randomUUID().toString().replace("-", ""));
        entity.setUserId(userId);
        entity.setModelType(modelType);
        entity.setModelName(modelName);
        entity.setProviderCode(str(body, "providerCode"));
        entity.setBaseUrl(str(body, "baseUrl"));
        entity.setConfigJson(jsonOrNull(body.get("configJson")));
        entity.setAuditStatus(0);
        entity.setStatus(1);
        entity.setHealthStatus(0);
        entity.setUsedCount(0L);
        entity.setQuotaLimit(null);
        entity.setRemark(str(body, "remark"));
        entity.setSort(0);

        // apiKey AES-256-GCM 加密落 api_key_cipher
        if (StringUtils.isNotBlank(apiKey)) {
            entity.setApiKeyCipher(AesGcmUtils.encrypt(apiKey, apiKeySecret));
        }

        sysUserCustomModelDao.insert(entity);
        auditService.log("custom", "create", "custom_model", entity.getId(),
                sanitizeBody(body), true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(Long userId, String id, Map<String, Object> body) {
        SysUserCustomModelEntity entity = requireOwned(userId, id);

        if (body.containsKey("modelName")) {
            String modelName = str(body, "modelName");
            if (StringUtils.isNotBlank(modelName) && !modelName.equals(entity.getModelName())) {
                LambdaQueryWrapper<SysUserCustomModelEntity> dupWrapper = new LambdaQueryWrapper<>();
                dupWrapper.eq(SysUserCustomModelEntity::getUserId, userId);
                dupWrapper.eq(SysUserCustomModelEntity::getModelType, entity.getModelType());
                dupWrapper.eq(SysUserCustomModelEntity::getModelName, modelName);
                dupWrapper.ne(SysUserCustomModelEntity::getId, id);
                if (sysUserCustomModelDao.selectCount(dupWrapper) > 0) {
                    throw new RenException(ErrorCode.CUSTOM_MODEL_DUPLICATE);
                }
                entity.setModelName(modelName);
            }
        }
        if (body.containsKey("providerCode")) {
            entity.setProviderCode(str(body, "providerCode"));
        }
        if (body.containsKey("baseUrl")) {
            entity.setBaseUrl(str(body, "baseUrl"));
        }
        if (body.containsKey("configJson")) {
            entity.setConfigJson(jsonOrNull(body.get("configJson")));
        }
        if (body.containsKey("remark")) {
            entity.setRemark(str(body, "remark"));
        }
        // apiKey 传空串/不传=不改；传非空新值=重新加密
        String apiKey = str(body, "apiKey");
        if (StringUtils.isNotBlank(apiKey)) {
            entity.setApiKeyCipher(AesGcmUtils.encrypt(apiKey, apiKeySecret));
        }

        sysUserCustomModelDao.updateById(entity);
        auditService.log("custom", "update", "custom_model", id, sanitizeBody(body), true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String id) {
        requireOwned(userId, id);
        sysUserCustomModelDao.deleteById(id);
        auditService.log("custom", "delete", "custom_model", id, null, true, null);
    }

    @Override
    public Map<String, Object> health(Long userId, String id) {
        SysUserCustomModelEntity entity = requireOwned(userId, id);

        Map<String, Object> result = new LinkedHashMap<>();
        if (StringUtils.isBlank(entity.getBaseUrl())) {
            result.put("status", 2);
            result.put("latencyMs", null);
            result.put("message", "baseUrl 为空");
            return result;
        }

        long start = System.currentTimeMillis();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(entity.getBaseUrl()))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();
            HttpResponse<Void> response = client.send(request, HttpResponse.BodyHandlers.discarding());
            long latency = System.currentTimeMillis() - start;

            int status = response.statusCode() >= 200 && response.statusCode() < 500 ? 1 : 2;
            result.put("status", status);
            result.put("latencyMs", latency);
            result.put("httpStatus", response.statusCode());

            // 回写健康状态
            SysUserCustomModelEntity patch = new SysUserCustomModelEntity();
            patch.setId(entity.getId());
            patch.setHealthStatus(status);
            sysUserCustomModelDao.updateById(patch);
        } catch (Exception e) {
            result.put("status", 2);
            result.put("latencyMs", System.currentTimeMillis() - start);
            result.put("message", e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());

            SysUserCustomModelEntity patch = new SysUserCustomModelEntity();
            patch.setId(entity.getId());
            patch.setHealthStatus(2);
            sysUserCustomModelDao.updateById(patch);
        }
        return result;
    }

    @Override
    public Map<String, Object> adminPage(Integer auditStatus, String modelType, String keyword, long page, long limit) {
        LambdaQueryWrapper<SysUserCustomModelEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(auditStatus != null, SysUserCustomModelEntity::getAuditStatus, auditStatus);
        wrapper.eq(StringUtils.isNotBlank(modelType), SysUserCustomModelEntity::getModelType,
                modelType == null ? null : modelType.toUpperCase());
        wrapper.and(StringUtils.isNotBlank(keyword), w -> w
                .like(SysUserCustomModelEntity::getModelName, keyword)
                .or().like(SysUserCustomModelEntity::getProviderCode, keyword));
        wrapper.orderByDesc(SysUserCustomModelEntity::getCreateDate);

        Page<SysUserCustomModelEntity> pager = new Page<>(page, limit);
        Page<SysUserCustomModelEntity> result = sysUserCustomModelDao.selectPage(pager, wrapper);

        List<Map<String, Object>> list = new ArrayList<>();
        for (SysUserCustomModelEntity e : result.getRecords()) {
            list.add(toVo(e, false));
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("list", list);
        data.put("total", result.getTotal());
        return data;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void audit(String id, boolean pass, String remark) {
        SysUserCustomModelEntity entity = getById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.CUSTOM_MODEL_NOT_FOUND);
        }
        if (entity.getAuditStatus() != null && entity.getAuditStatus() != 0) {
            // 已审过允许改判（重审）
        }

        SysUserCustomModelEntity patch = new SysUserCustomModelEntity();
        patch.setId(id);
        patch.setAuditStatus(pass ? 1 : 2);
        patch.setAuditRemark(remark);
        patch.setAuditor(SecurityUser.getUserId());
        patch.setAuditDate(new Date());
        sysUserCustomModelDao.updateById(patch);

        auditService.log("custom", "audit", "custom_model", id,
                Map.of("pass", pass, "remark", remark == null ? "" : remark), true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void setQuota(String id, Integer quotaLimit) {
        SysUserCustomModelEntity entity = getById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.CUSTOM_MODEL_NOT_FOUND);
        }
        SysUserCustomModelEntity patch = new SysUserCustomModelEntity();
        patch.setId(id);
        patch.setQuotaLimit(quotaLimit);
        sysUserCustomModelDao.updateById(patch);

        auditService.log("custom", "quota", "custom_model", id, Map.of("quotaLimit", quotaLimit), true, null);
    }

    @Override
    public List<Map<String, Object>> listApprovedAsResources(Long userId, String modelType) {
        if (userId == null || StringUtils.isBlank(modelType)) {
            return new ArrayList<>();
        }
        LambdaQueryWrapper<SysUserCustomModelEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserCustomModelEntity::getUserId, userId);
        wrapper.eq(SysUserCustomModelEntity::getModelType, modelType.toUpperCase());
        wrapper.eq(SysUserCustomModelEntity::getAuditStatus, 1);
        wrapper.eq(SysUserCustomModelEntity::getStatus, 1);
        wrapper.orderByAsc(SysUserCustomModelEntity::getSort);

        List<Map<String, Object>> result = new ArrayList<>();
        for (SysUserCustomModelEntity e : sysUserCustomModelDao.selectList(wrapper)) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", e.getId());
            item.put("modelName", e.getModelName());
            item.put("source", "custom");
            result.add(item);
        }
        return result;
    }

    @Override
    public SysUserCustomModelEntity getById(String id) {
        return sysUserCustomModelDao.selectById(id);
    }

    // ==================== 私有工具 ====================

    private SysUserCustomModelEntity requireOwned(Long userId, String id) {
        SysUserCustomModelEntity entity = sysUserCustomModelDao.selectById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.CUSTOM_MODEL_NOT_FOUND);
        }
        if (!entity.getUserId().equals(userId)) {
            throw new RenException(ErrorCode.CUSTOM_MODEL_NOT_FOUND);
        }
        return entity;
    }

    /** VO：apiKey 永远掩码（解密后前4+****） */
    private Map<String, Object> toVo(SysUserCustomModelEntity e, boolean withKeyMask) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", e.getId());
        vo.put("userId", e.getUserId());
        vo.put("modelType", e.getModelType());
        vo.put("modelName", e.getModelName());
        vo.put("providerCode", e.getProviderCode());
        vo.put("baseUrl", e.getBaseUrl());
        vo.put("auditStatus", e.getAuditStatus());
        vo.put("auditRemark", e.getAuditRemark());
        vo.put("status", e.getStatus());
        vo.put("healthStatus", e.getHealthStatus());
        vo.put("quotaLimit", e.getQuotaLimit());
        vo.put("usedCount", e.getUsedCount());
        vo.put("remark", e.getRemark());
        vo.put("createDate", e.getCreateDate());
        if (StringUtils.isNotBlank(e.getConfigJson())) {
            try {
                vo.put("configJson", xiaozhi.common.utils.JsonUtils.parseObject(e.getConfigJson(), Object.class));
            } catch (Exception ignore) {
                vo.put("configJson", e.getConfigJson());
            }
        }
        if (withKeyMask && StringUtils.isNotBlank(e.getApiKeyCipher())) {
            try {
                String plain = AesGcmUtils.decrypt(e.getApiKeyCipher(), apiKeySecret);
                vo.put("apiKeyMasked", AesGcmUtils.mask(plain));
            } catch (Exception ignore) {
                vo.put("apiKeyMasked", "****");
            }
        }
        return vo;
    }

    /** 审计参数脱敏（apiKey 移除） */
    private Map<String, Object> sanitizeBody(Map<String, Object> body) {
        Map<String, Object> safe = new LinkedHashMap<>(body);
        safe.remove("apiKey");
        return safe;
    }

    private String str(Map<String, Object> body, String key) {
        Object v = body.get(key);
        return v == null ? null : String.valueOf(v);
    }

    private String jsonOrNull(Object v) {
        if (v == null) {
            return null;
        }
        if (v instanceof String s) {
            return s.isBlank() ? null : s;
        }
        return xiaozhi.common.utils.JsonUtils.toJsonString(v);
    }
}
