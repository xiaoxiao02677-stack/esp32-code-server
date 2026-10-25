package yuhe.modules.sys.controller;

import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import org.apache.shiro.SecurityUtils;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import yuhe.common.annotation.LogOperation;
import yuhe.common.constant.Constant;
import yuhe.common.exception.RenException;
import yuhe.common.exception.ErrorCode;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.common.validator.AssertUtils;
import yuhe.common.validator.ValidatorUtils;
import yuhe.common.validator.group.AddGroup;
import yuhe.common.validator.group.DefaultGroup;
import yuhe.common.validator.group.UpdateGroup;
import yuhe.modules.config.service.ConfigService;
import yuhe.common.user.UserDetail;
import yuhe.modules.sys.dto.SysParamsDTO;
import yuhe.modules.sys.enums.SuperAdminEnum;
import yuhe.modules.sys.service.SysParamsService;
import yuhe.modules.sys.utils.WebSocketValidator;

import java.util.List;
import java.util.Set;

/**
 * 参数管理
 *
 * @author Mark sunlightcs@gmail.com
 * @since 1.0.0
 */
@RestController
@RequestMapping("admin/params")
@Tag(name = "参数管理")
@AllArgsConstructor
public class SysParamsController {
    private final SysParamsService sysParamsService;
    private final ConfigService configService;
    private final RestTemplate restTemplate;

    /**
     * 敏感参数键：值含服务器间密钥 / 第三方 API 密钥 / 支付密钥等。
     * 展示配置若给普通用户勾了 /admin/params（Oauth2Realm 会发 admin:params 码），
     * 非超管仍可在注解层放行——这里做纵深防御：非超管读取时值一律掩码，
     * 写操作（save/update/delete）非超管直接拒绝。密钥明文只对超管可见。
     */
    private static final Set<String> SENSITIVE_PREFIXES = Set.of(
            "server.secret", "pay.", "sms.", "mail.", "smtp.");

    private static boolean isSuperAdmin() {
        Object principal = SecurityUtils.getSubject() != null ? SecurityUtils.getSubject().getPrincipal() : null;
        return principal instanceof UserDetail u
                && Integer.valueOf(SuperAdminEnum.YES.value()).equals(u.getSuperAdmin());
    }

    private static boolean isSensitive(String paramCode) {
        if (paramCode == null) {
            return false;
        }
        String code = paramCode.toLowerCase();
        return SENSITIVE_PREFIXES.stream().anyMatch(code::startsWith)
                || code.contains("secret") || code.contains("apikey") || code.contains("api_key")
                || code.contains("appkey") || code.contains("accesskey") || code.contains("token");
    }

    /** 非超管：敏感参数值掩码（前4后4），短值全打码 */
    private static String mask(String value) {
        if (value == null || value.isEmpty()) {
            return value;
        }
        if (value.length() <= 8) {
            return "****";
        }
        return value.substring(0, 4) + "****" + value.substring(value.length() - 4);
    }

    private void maskSensitive(List<SysParamsDTO> list) {
        if (isSuperAdmin()) {
            return;
        }
        for (SysParamsDTO dto : list) {
            if (isSensitive(dto.getParamCode())) {
                dto.setParamValue(mask(dto.getParamValue()));
            }
        }
    }

    @GetMapping("page")
    @Operation(summary = "分页")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", in = ParameterIn.QUERY, required = true, ref = "int"),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", in = ParameterIn.QUERY, required = true, ref = "int"),
            @Parameter(name = Constant.ORDER_FIELD, description = "排序字段", in = ParameterIn.QUERY, ref = "String"),
            @Parameter(name = Constant.ORDER, description = "排序方式，可选值(asc、desc)", in = ParameterIn.QUERY, ref = "String"),
            @Parameter(name = "paramCode", description = "参数编码或参数备注", in = ParameterIn.QUERY, ref = "String")
    })
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<PageData<SysParamsDTO>> page(@Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<SysParamsDTO> page = sysParamsService.page(params);
        maskSensitive(page.getList());
        return new Result<PageData<SysParamsDTO>>().ok(page);
    }

    @GetMapping("{id}")
    @Operation(summary = "信息")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<SysParamsDTO> get(@PathVariable("id") Long id) {
        SysParamsDTO data = sysParamsService.get(id);
        if (data != null && !isSuperAdmin() && isSensitive(data.getParamCode())) {
            data.setParamValue(mask(data.getParamValue()));
        }
        return new Result<SysParamsDTO>().ok(data);
    }

    @PostMapping
    @Operation(summary = "保存")
    @LogOperation("保存")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<Void> save(@RequestBody SysParamsDTO dto) {
        // 参数写入影响全站服务行为，仅超管可操作（纵深防御：展示配置错配也不放权）
        if (!isSuperAdmin()) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        // 效验数据
        ValidatorUtils.validateEntity(dto, AddGroup.class, DefaultGroup.class);

        sysParamsService.save(dto);
        configService.getConfig(false);
        return new Result<Void>();
    }

    @PutMapping
    @Operation(summary = "修改")
    @LogOperation("修改")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<Void> update(@RequestBody SysParamsDTO dto) {
        // 参数写入影响全站服务行为，仅超管可操作（纵深防御：展示配置错配也不放权）
        if (!isSuperAdmin()) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        // 效验数据
        ValidatorUtils.validateEntity(dto, UpdateGroup.class, DefaultGroup.class);

        // 验证WebSocket地址列表
        validateWebSocketUrls(dto.getParamCode(), dto.getParamValue());

        // 验证OTA地址
        validateOtaUrl(dto.getParamCode(), dto.getParamValue());

        // 验证MCP地址
        validateMcpUrl(dto.getParamCode(), dto.getParamValue());

        // 验证声纹地址
        validateVoicePrint(dto.getParamCode(), dto.getParamValue());

        // 校验mqtt密钥长度
        validateMqttSecretLength(dto.getParamCode(), dto.getParamValue());

        // 如果是系统功能菜单配置，使用特殊处理
        if (Constant.SYSTEM_WEB_MENU.equals(dto.getParamCode())) {
            sysParamsService.updateSystemWebMenu(dto.getParamValue());
        } else {
            sysParamsService.update(dto);
        }
        configService.getConfig(false);
        return new Result<Void>();
    }

    /**
     * 验证WebSocket地址列表
     *
     * @param urls WebSocket地址列表，以分号分隔
     * @return 验证结果
     */
    private void validateWebSocketUrls(String paramCode, String urls) {
        if (!paramCode.equals(Constant.SERVER_WEBSOCKET)) {
            return;
        }
        String[] wsUrls = urls.split("\\;");
        if (wsUrls.length == 0) {
            throw new RenException(ErrorCode.WEBSOCKET_URLS_EMPTY);
        }
        for (String url : wsUrls) {
            if (StringUtils.isNotBlank(url)) {
                // 检查是否包含localhost或127.0.0.1
                if (url.contains("localhost") || url.contains("127.0.0.1")) {
                    throw new RenException(ErrorCode.WEBSOCKET_URL_LOCALHOST);
                }

                // 验证WebSocket地址格式
                if (!WebSocketValidator.validateUrlFormat(url)) {
                    throw new RenException(ErrorCode.WEBSOCKET_URL_FORMAT_ERROR);
                }

                // 测试WebSocket连接
                if (!WebSocketValidator.testConnection(url)) {
                    throw new RenException(ErrorCode.WEBSOCKET_CONNECTION_FAILED);
                }
            }
        }
    }

    @PostMapping("/delete")
    @Operation(summary = "删除")
    @LogOperation("删除")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<Void> delete(@RequestBody String[] ids) {
        // 参数删除影响全站服务行为，仅超管可操作（纵深防御）
        if (!isSuperAdmin()) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        // 效验数据
        AssertUtils.isArrayEmpty(ids, "id");

        sysParamsService.delete(ids);
        configService.getConfig(false);
        return new Result<Void>();
    }

    /**
     * 验证OTA地址
     */
    private void validateOtaUrl(String paramCode, String url) {
        if (!paramCode.equals(Constant.SERVER_OTA)) {
            return;
        }
        if (StringUtils.isBlank(url) || url.equals("null")) {
            return;
        }

        // 检查是否包含localhost或127.0.0.1
        if (url.contains("localhost") || url.contains("127.0.0.1")) {
            throw new RenException(ErrorCode.OTA_URL_LOCALHOST);
        }

        // 验证URL格式
        if (!url.toLowerCase().startsWith("http")) {
            throw new RenException(ErrorCode.OTA_URL_PROTOCOL_ERROR);
        }
        if (!url.endsWith("/ota/")) {
            throw new RenException(ErrorCode.OTA_URL_FORMAT_ERROR);
        }

        try {
            // 发送GET请求
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            if (response.getStatusCode() != HttpStatus.OK) {
                throw new RenException(ErrorCode.OTA_INTERFACE_ACCESS_FAILED);
            }
            // 检查响应内容是否包含OTA相关信息
            String body = response.getBody();
            if (body == null || !body.contains("OTA")) {
                throw new RenException(ErrorCode.OTA_INTERFACE_FORMAT_ERROR);
            }
        } catch (Exception e) {
            throw new RenException(ErrorCode.OTA_INTERFACE_VALIDATION_FAILED);
        }
    }

    private void validateMcpUrl(String paramCode, String url) {
        if (!paramCode.equals(Constant.SERVER_MCP_ENDPOINT)) {
            return;
        }
        if (StringUtils.isBlank(url) || url.equals("null")) {
            return;
        }
        if (url.contains("localhost") || url.contains("127.0.0.1")) {
            throw new RenException(ErrorCode.MCP_URL_LOCALHOST);
        }
        if (!url.toLowerCase().contains("key")) {
            throw new RenException(ErrorCode.MCP_URL_INVALID);
        }

        try {
            // 发送GET请求
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            if (response.getStatusCode() != HttpStatus.OK) {
                throw new RenException(ErrorCode.MCP_INTERFACE_ACCESS_FAILED);
            }
            // 检查响应内容是否包含mcp相关信息
            String body = response.getBody();
            if (body == null || !body.contains("success")) {
                throw new RenException(ErrorCode.MCP_INTERFACE_FORMAT_ERROR);
            }
        } catch (Exception e) {
            throw new RenException(ErrorCode.MCP_INTERFACE_VALIDATION_FAILED);
        }
    }

    // 验证声纹接口地址是否正常
    private void validateVoicePrint(String paramCode, String url) {
        if (!paramCode.equals(Constant.SERVER_VOICE_PRINT)) {
            return;
        }
        if (StringUtils.isBlank(url) || url.equals("null")) {
            return;
        }
        if (url.contains("localhost") || url.contains("127.0.0.1")) {
            throw new RenException(ErrorCode.VOICEPRINT_URL_LOCALHOST);
        }
        if (!url.toLowerCase().contains("key")) {
            throw new RenException(ErrorCode.VOICEPRINT_URL_INVALID);
        }
        // 验证URL格式
        if (!url.toLowerCase().startsWith("http")) {
            throw new RenException(ErrorCode.VOICEPRINT_URL_PROTOCOL_ERROR);
        }
        try {
            // 发送GET请求
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            if (response.getStatusCode() != HttpStatus.OK) {
                throw new RenException(ErrorCode.VOICEPRINT_INTERFACE_ACCESS_FAILED);
            }
            // 检查响应内容
            String body = response.getBody();
            if (body == null || !body.contains("healthy")) {
                throw new RenException(ErrorCode.VOICEPRINT_INTERFACE_FORMAT_ERROR);
            }
        } catch (Exception e) {
            throw new RenException(ErrorCode.VOICEPRINT_INTERFACE_VALIDATION_FAILED);
        }
    }

    // 校验mqtt密钥长度和复杂度
    private void validateMqttSecretLength(String paramCode, String secret) {
        if (!paramCode.equals(Constant.SERVER_MQTT_SECRET)) {
            return;
        }
        if (StringUtils.isBlank(secret) || secret.equals("null")) {
            throw new RenException(ErrorCode.MQTT_SECRET_EMPTY);
        }
        if (secret.length() < 8) {
            throw new RenException(ErrorCode.MQTT_SECRET_LENGTH_INSECURE);
        }
        // 检查是否同时包含大小写字母
        if (!secret.matches(".*[a-z].*") || !secret.matches(".*[A-Z].*")) {
            throw new RenException(ErrorCode.MQTT_SECRET_CHARACTER_INSECURE);
        }
        // 不允许包含弱密码
        String[] weakPasswords = { "test", "1234", "admin", "password", "qwerty", "yuhe" };
        for (String weakPassword : weakPasswords) {
            if (secret.toLowerCase().contains(weakPassword)) {
                throw new RenException(ErrorCode.MQTT_SECRET_WEAK_PASSWORD);
            }
        }
    }
}
