package yuhe.modules.device.filter;

import java.io.IOException;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;

/**
 * OTA 路径重复斜杠归一化过滤器
 *
 * 背景：固件 main/ota.cc 的 Ota::CheckConfigVersion() 直接拼接
 *   GetCheckVersionUrl() + "/config/version?device_id=..."
 * 而 CONFIG_OTA_URL 本身以 "/" 结尾（http://host:8002/yuhe/ota/），
 * 实际请求路径为 /yuhe/ota//config/version，Spring 的路径匹配不会把
 * 连续斜杠视为等价，端点将 404，导致设备每次启动的配置同步失败。
 *
 * 处理范围严格限定：仅当 URI 同时含 "//" 与 "/ota/" 时才归一并放行，
 * 其余请求原样透传，避免影响全局路由行为。
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class OtaSlashNormalizeFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        String uri = request.getRequestURI();
        if (uri != null && uri.contains("//") && uri.contains("/ota/")) {
            String normalized = uri.replaceAll("/{2,}", "/");
            log.info("[ota-config] 归一化重复斜杠: {} -> {}", uri, normalized);
            filterChain.doFilter(new HttpServletRequestWrapper(request) {
                @Override
                public String getRequestURI() {
                    return normalized;
                }
            }, response);
            return;
        }
        filterChain.doFilter(request, response);
    }
}
