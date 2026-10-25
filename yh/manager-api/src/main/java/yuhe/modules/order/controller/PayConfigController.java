package yuhe.modules.order.controller;

import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import yuhe.common.utils.Result;
import yuhe.modules.sys.dao.SysParamsDao;
import yuhe.modules.sys.entity.SysParamsEntity;
import yuhe.modules.sys.redis.SysParamsRedis;

/**
 * 电商小店-支付配置（管理端商品页「支付设置」弹窗后端）。
 * 读写 sys_params 的 pay.* 键：
 *   XDDPay（小多支付）：pay.xddpay.appId / pay.xddpay.secret / pay.xddpay.notifyUrl
 *   支付宝（官方直连）：pay.alipay.*——只回显配置状态，不回显任何密钥
 * 权限与 admin/params 一致（超管或 admin:params）；写后同步 sysParamsRedis 缓存
 * （XddpayService/ShopPayService 读值走 getValueByCode 直查 DB，即时生效）。
 */
@RestController
@RequestMapping("/goods/pay-config")
public class PayConfigController {

    private final SysParamsDao sysParamsDao;
    private final SysParamsRedis sysParamsRedis;

    public PayConfigController(SysParamsDao sysParamsDao, SysParamsRedis sysParamsRedis) {
        this.sysParamsDao = sysParamsDao;
        this.sysParamsRedis = sysParamsRedis;
    }

    /** 读取支付配置：XDDPay 三键（secret 掩码回显）+ 支付宝配置状态（仅 appId/网关/是否就绪） */
    @GetMapping
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<Map<String, Object>> get() {
        Map<String, Object> r = new LinkedHashMap<>();

        String appId = param("pay.xddpay.appId");
        String secret = param("pay.xddpay.secret");
        String notifyUrl = param("pay.xddpay.notifyUrl");
        Map<String, Object> xddpay = new LinkedHashMap<>();
        xddpay.put("appId", appId == null ? "" : appId);
        xddpay.put("secret", mask(secret));
        xddpay.put("notifyUrl", notifyUrl == null ? "" : notifyUrl);
        xddpay.put("configured", appId != null && secret != null);
        r.put("xddpay", xddpay);

        Map<String, Object> alipay = new LinkedHashMap<>();
        String alipayAppId = param("pay.alipay.appId");
        alipay.put("appId", alipayAppId == null ? "" : alipayAppId);
        alipay.put("gateway", param("pay.alipay.gateway"));
        alipay.put("configured", alipayAppId != null
                && param("pay.alipay.privateKey") != null && param("pay.alipay.publicKey") != null);
        r.put("alipay", alipay);

        return new Result<Map<String, Object>>().ok(r);
    }

    /**
     * 保存 XDDPay 配置：body = { appId, secret, notifyUrl }。
     * secret 传掩码值（含 ****）表示不变更；字段传 null/缺省表示不动，传空串表示清除
     * （写空串即可，读取侧把空串视为未配置）。
     */
    @PutMapping
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:params"}, logical = Logical.OR)
    public Result<Map<String, Object>> save(@RequestBody Map<String, String> body) {
        String appId = body.get("appId");
        String secret = body.get("secret");
        String notifyUrl = body.get("notifyUrl");

        if (appId != null && !appId.trim().isEmpty() && !appId.trim().matches("\\d+")) {
            return new Result<Map<String, Object>>().error("XDDPay App ID 必须为纯数字");
        }

        upsert("pay.xddpay.appId", appId, "XDDPay 应用ID（商户后台-应用管理）", "number");
        if (secret != null && !secret.contains("****")) {
            upsert("pay.xddpay.secret", secret, "XDDPay 通信密钥（签名计算用）", "string");
        }
        upsert("pay.xddpay.notifyUrl", notifyUrl, "XDDPay 异步通知地址（须公网可达，并填到商户后台）", "string");

        return get();
    }

    /** 存在则 UPDATE，不存在则 INSERT（param_type=1 非系统参数，参数管理页可见）；两种路径都同步 Redis 缓存 */
    private void upsert(String code, String value, String remark, String valueType) {
        if (value == null) {
            return;
        }
        String v = value.trim();
        int rows = sysParamsDao.updateValueByCode(code, v);
        if (rows == 0) {
            SysParamsEntity e = new SysParamsEntity();
            e.setParamCode(code);
            e.setParamValue(v);
            e.setValueType(valueType);
            e.setParamType(1);
            e.setRemark(remark);
            sysParamsDao.insert(e);
        }
        sysParamsRedis.set(code, v);
    }

    private String param(String code) {
        try {
            String v = sysParamsDao.getValueByCode(code);
            return v == null || v.trim().isEmpty() ? null : v.trim();
        } catch (Exception e) {
            return null;
        }
    }

    /** 密钥掩码：短密钥全遮，长的保留前4后4 */
    static String mask(String s) {
        if (s == null) {
            return "";
        }
        if (s.length() <= 8) {
            return "****";
        }
        return s.substring(0, 4) + "****" + s.substring(s.length() - 4);
    }
}
