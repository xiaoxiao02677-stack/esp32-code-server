package yuhe.common.config;

import org.apache.catalina.LifecycleException;
import org.apache.catalina.valves.rewrite.RewriteValve;

/**
 * 预置重写规则的 RewriteValve。
 *
 * 直接在 WebServerFactoryCustomizer 里调 setConfiguration() 会 NPE：
 * setConfiguration 内部 getContainer().getLogName()，而 customizer 阶段
 * valve 尚未挂到 Context。改为延迟到 startInternal（此时 container 已挂载）
 * 再注入规则；随后的 super.startInternal() 找不到 /WEB-INF/rewrite.config
 * 等文件时直接 return，预置规则得以保留。
 */
public class ConfiguredRewriteValve extends RewriteValve {

    private final String rulesConfig;

    public ConfiguredRewriteValve(String rulesConfig) {
        this.rulesConfig = rulesConfig;
    }

    @Override
    protected void startInternal() throws LifecycleException {
        try {
            setConfiguration(rulesConfig);
        } catch (Exception e) {
            throw new LifecycleException("注入旧路径重写规则失败", e);
        }
        super.startInternal();
    }
}
