package yuhe.modules.config.init;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

import jakarta.annotation.PostConstruct;
import yuhe.common.constant.Constant;
import yuhe.common.redis.RedisKeys;
import yuhe.common.redis.RedisUtils;
import yuhe.modules.config.service.ConfigService;
import yuhe.modules.device.service.DeviceAddressBookService;
import yuhe.modules.sys.service.SysParamsService;

@Configuration
@DependsOn("liquibase")
public class SystemInitConfig {

    @Autowired
    private SysParamsService sysParamsService;

    @Autowired
    private ConfigService configService;

    @Autowired
    private RedisUtils redisUtils;

    @Autowired
    private DeviceAddressBookService deviceAddressBookService;

    @PostConstruct
    public void init() {
        // 检查版本号
        String redisVersion = (String) redisUtils.get(RedisKeys.getVersionKey());
        if (!Constant.VERSION.equals(redisVersion)) {
            // 如果版本不一致，清空Redis
            redisUtils.emptyAll();
            // 存储新版本号
            redisUtils.set(RedisKeys.getVersionKey(), Constant.VERSION);
        }

        sysParamsService.initServerSecret();
        configService.getConfig(false);

        // 初始化设备通讯录缓存
        deviceAddressBookService.refreshCache();
    }
}