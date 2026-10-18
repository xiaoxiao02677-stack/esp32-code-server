package yuhe.common.config;

import org.apache.catalina.valves.rewrite.RewriteValve;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 旧路径兼容：项目由 xiaozhi 更名 yuhe 后，已烧录固件的 OTA URL 仍指向
 * http://host:8002/xiaozhi/ota/。RewriteValve 在连接器层把 /xiaozhi/* 内部
 * 重写为 /yuhe/*（设备无感知、无 301 往返），旧设备可继续完成 OTA 与配置拉取。
 *
 * 迁移完成（所有在役固件都换成 /yuhe 路径）后可整体删除本类。
 */
@Configuration
public class LegacyPathCompatConfig {

    @Bean
    public WebServerFactoryCustomizer<TomcatServletWebServerFactory> legacyXiaozhiPathRewrite() {
        return factory -> factory.addContextValves(new RewriteValve() {{
            setConfiguration(
                "RewriteCond %{REQUEST_URI} ^/xiaozhi/(.*)$\n" +
                "RewriteRule ^/xiaozhi/(.*)$ /yuhe/$1 [L]\n"
            );
        }});
    }
}
