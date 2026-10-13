package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;

import org.apache.commons.lang3.StringUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import jakarta.servlet.http.HttpServletRequest;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.common.utils.HttpContextUtils;
import xiaozhi.common.utils.IpUtils;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.dao.SysAuditLogDao;
import xiaozhi.modules.sys.entity.SysAuditLogEntity;
import xiaozhi.modules.sys.service.AuditService;
import xiaozhi.modules.sys.service.SysAuditLogService;
import xiaozhi.modules.sys.vo.SysAuditLogVO;

/**
 * 审计日志实现：
 * - 异步落库（CompletableFuture.runAsync），不阻塞业务请求
 * - 操作人/请求上下文自行获取（无登录上下文时 user 置 null）
 * - params 递归脱敏（password/apiKey/secret/token 忽略大小写移除）
 */
@Service
@AllArgsConstructor
public class SysAuditLogServiceImpl extends BaseServiceImpl<SysAuditLogDao, SysAuditLogEntity>
        implements AuditService, SysAuditLogService {

    private static final Logger logger = LoggerFactory.getLogger(SysAuditLogServiceImpl.class);

    /** 需要脱敏移除的字段（忽略大小写） */
    private static final Set<String> SENSITIVE_KEYS = new HashSet<>(
            Arrays.asList("password", "apikey", "secret", "token", "newpassword", "oldpassword", "captcha"));

    @Override
    public void log(String module, String operation, String targetType, String targetId,
            Object params, boolean success, String errorMsg) {
        try {
            SysAuditLogEntity entity = new SysAuditLogEntity();
            entity.setModule(module);
            entity.setOperation(operation);
            entity.setTargetType(targetType);
            entity.setTargetId(targetId == null ? null : targetId.length() > 64 ? targetId.substring(0, 64) : targetId);
            entity.setResult(success ? 1 : 0);
            entity.setErrorMsg(errorMsg == null ? null
                    : errorMsg.length() > 500 ? errorMsg.substring(0, 500) : errorMsg);

            // 操作人（无登录上下文时置 null）
            try {
                var user = SecurityUser.getUser();
                if (user != null && user.getId() != null) {
                    entity.setUserId(user.getId());
                    entity.setUsername(user.getUsername());
                }
            } catch (Exception ignore) {
                // anon 上下文
            }

            // 请求上下文
            try {
                HttpServletRequest request = HttpContextUtils.getHttpServletRequest();
                if (request != null) {
                    entity.setRequestUri(truncate(request.getRequestURI(), 255));
                    entity.setRequestMethod(request.getMethod());
                    entity.setIp(IpUtils.getIpAddr(request));
                    entity.setUserAgent(truncate(request.getHeader("User-Agent"), 500));
                }
            } catch (Exception ignore) {
                // 异步线程无请求上下文（此时 URI 已由切面在主线程预取）
            }

            // params 脱敏
            String paramsJson = sanitizeParams(params);
            if (paramsJson != null && paramsJson.length() > 4000) {
                paramsJson = paramsJson.substring(0, 4000);
            }
            entity.setParams(paramsJson);

            // 异步落库
            final SysAuditLogEntity finalEntity = entity;
            CompletableFuture.runAsync(() -> {
                try {
                    baseDao.insert(finalEntity);
                } catch (Exception e) {
                    logger.warn("审计日志落库失败 module={} op={} err={}", module, operation, e.getMessage());
                }
            });
        } catch (Exception e) {
            // 审计失败绝不影响业务
            logger.warn("审计日志构建失败 module={} op={} err={}", module, operation, e.getMessage());
        }
    }

    /** 查询：分页 + 过滤 */
    @Override
    public PageData<SysAuditLogVO> page(Map<String, Object> params) {
        QueryWrapper<SysAuditLogEntity> wrapper = new QueryWrapper<>();
        String userId = (String) params.get("userId");
        String module = (String) params.get("module");
        String operation = (String) params.get("operation");
        String startDate = (String) params.get("startDate");
        String endDate = (String) params.get("endDate");

        if (StringUtils.isBlank(userId) && StringUtils.isBlank(module) && StringUtils.isBlank(operation)
                && StringUtils.isBlank(startDate) && StringUtils.isBlank(endDate)
                && params.get(Constant.PAGE) == null && params.get(Constant.LIMIT) == null) {
            throw new RenException(ErrorCode.AUDIT_QUERY_INVALID);
        }

        wrapper.eq(StringUtils.isNotBlank(userId), "user_id", userId);
        wrapper.eq(StringUtils.isNotBlank(module), "module", module);
        wrapper.eq(StringUtils.isNotBlank(operation), "operation", operation);
        wrapper.ge(StringUtils.isNotBlank(startDate), "created_at", startDate);
        wrapper.le(StringUtils.isNotBlank(endDate), "created_at", endDate + (endDate != null && endDate.length() == 10 ? " 23:59:59" : ""));
        wrapper.orderByDesc("id");

        IPage<SysAuditLogEntity> page = baseDao.selectPage(getPage(params, "id", false), wrapper);

        List<SysAuditLogVO> voList = new ArrayList<>();
        for (SysAuditLogEntity e : page.getRecords()) {
            SysAuditLogVO vo = new SysAuditLogVO();
            vo.setId(e.getId());
            vo.setUserId(e.getUserId());
            vo.setUsername(e.getUsername());
            vo.setModule(e.getModule());
            vo.setOperation(e.getOperation());
            vo.setTargetType(e.getTargetType());
            vo.setTargetId(e.getTargetId());
            vo.setRequestUri(e.getRequestUri());
            vo.setRequestMethod(e.getRequestMethod());
            vo.setResult(e.getResult());
            vo.setErrorMsg(e.getErrorMsg());
            vo.setIp(e.getIp());
            vo.setUserAgent(e.getUserAgent());
            vo.setDuration(e.getDuration());
            vo.setCreatedAt(e.getCreatedAt());
            // params JSON 字符串 → 对象输出
            if (StringUtils.isNotBlank(e.getParams())) {
                try {
                    vo.setParams(JsonUtils.parseObject(e.getParams(), Object.class));
                } catch (Exception ignore) {
                    vo.setParams(e.getParams());
                }
            }
            voList.add(vo);
        }
        return new PageData<>(voList, page.getTotal());
    }

    /** 去重 module 列表 */
    @Override
    public List<String> listModules() {
        return baseDao.selectDistinctModules();
    }

    // ==================== 脱敏工具 ====================

    /** params 任意对象 → 脱敏后 JSON 字符串 */
    private String sanitizeParams(Object params) {
        if (params == null) {
            return null;
        }
        try {
            String json = JsonUtils.toJsonString(params);
            com.fasterxml.jackson.databind.JsonNode node = JsonUtils.parseObject(json,
                    com.fasterxml.jackson.databind.JsonNode.class);
            if (node == null) {
                return null;
            }
            com.fasterxml.jackson.databind.JsonNode sanitized = sanitizeNode(node);
            return sanitized == null ? null : sanitized.toString();
        } catch (Exception e) {
            // 无法序列化的对象降级为 toString 截断
            return truncate(String.valueOf(params), 4000);
        }
    }

    /** 递归移除敏感 key */
    private com.fasterxml.jackson.databind.JsonNode sanitizeNode(com.fasterxml.jackson.databind.JsonNode node) {
        if (node == null) {
            return null;
        }
        if (node.isObject()) {
            ObjectNode obj = (ObjectNode) node;
            List<String> toRemove = new ArrayList<>();
            obj.fieldNames().forEachRemaining(f -> {
                if (SENSITIVE_KEYS.contains(f.toLowerCase())) {
                    toRemove.add(f);
                }
            });
            toRemove.forEach(obj::remove);
            obj.fieldNames().forEachRemaining(f -> {
                com.fasterxml.jackson.databind.JsonNode child = obj.get(f);
                com.fasterxml.jackson.databind.JsonNode cleaned = sanitizeNode(child);
                if (cleaned != child && cleaned != null) {
                    obj.set(f, cleaned);
                }
            });
            return obj;
        }
        if (node.isArray()) {
            ArrayNode arr = (ArrayNode) node;
            for (int i = 0; i < arr.size(); i++) {
                com.fasterxml.jackson.databind.JsonNode cleaned = sanitizeNode(arr.get(i));
                if (cleaned != arr.get(i) && cleaned != null) {
                    arr.set(i, cleaned);
                }
            }
            return arr;
        }
        return node;
    }

    private String truncate(String s, int max) {
        if (s == null) {
            return null;
        }
        return s.length() > max ? s.substring(0, max) : s;
    }
}
