package xiaozhi.common.aspect;

import java.lang.reflect.Method;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.aspectj.lang.reflect.MethodSignature;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import jakarta.servlet.http.HttpServletRequest;
import xiaozhi.common.annotation.LogOperation;
import xiaozhi.modules.sys.service.AuditService;

/**
 * 操作日志切面（@LogOperation 兜底通用埋点）
 * Copyright (c) 人人开源 All rights reserved.
 * Website: https://www.renren.io
 *
 * module 取注解 value 前缀（冒号前）；operation 取冒号后（无冒号则整串作 operation，module=op）。
 */
@Aspect
@Component
public class LogOperationAspect {
    private static final Logger logger = LoggerFactory.getLogger(LogOperationAspect.class);

    private final AuditService auditService;

    public LogOperationAspect(AuditService auditService) {
        this.auditService = auditService;
    }

    @Pointcut("@annotation(xiaozhi.common.annotation.LogOperation)")
    public void logOperationPointCut() {
    }

    @Around("logOperationPointCut()")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        long beginTime = System.currentTimeMillis();
        Throwable error = null;
        Object result = null;
        try {
            result = point.proceed();
            return result;
        } catch (Throwable e) {
            error = e;
            throw e;
        } finally {
            try {
                saveLog(point, System.currentTimeMillis() - beginTime, error);
            } catch (Exception e) {
                logger.warn("保存操作日志失败：{}", e.getMessage());
            }
        }
    }

    private void saveLog(ProceedingJoinPoint joinPoint, long duration, Throwable error) {
        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        Method method = signature.getMethod();
        LogOperation annotation = method.getAnnotation(LogOperation.class);
        if (annotation == null) {
            return;
        }

        // value 形如 "sys:user:save" → module=sys:user, operation=save；无冒号 → module=op=value
        String value = annotation.value();
        String module;
        String operation;
        int lastColon = value.lastIndexOf(':');
        if (lastColon > 0) {
            module = value.substring(0, lastColon);
            operation = value.substring(lastColon + 1);
        } else {
            module = "op";
            operation = value;
        }

        // 请求上下文
        String uri = null;
        String requestMethod = null;
        try {
            ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
            if (attrs != null) {
                HttpServletRequest request = attrs.getRequest();
                uri = request.getRequestURI();
                requestMethod = request.getMethod();
            }
        } catch (Exception ignore) {
        }

        // 参数（脱敏交给 AuditService）
        Object params = joinPoint.getArgs();

        auditService.log(module, operation, "method", method.getName(), params,
                error == null, error == null ? null : String.valueOf(error.getMessage()));
    }
}
