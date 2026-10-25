package yuhe.modules.order.service;

import java.math.BigDecimal;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import yuhe.common.utils.JsonUtils;
import yuhe.modules.order.controller.ShopPaymentMapper;
import yuhe.modules.order.dao.OrderMapper;
import yuhe.modules.sys.dao.SysParamsDao;

/**
 * XDDPay 支付服务（1:1 复刻商城 yy-personal-pay.php v4.2）。
 *
 * 网关：https://gateway.xddpay.com（POST 表单跳转）
 * 签名：MD5(order_no=X&subject=X&pay_type=X&money=X&app_id=X&extra=X&secret) 转大写
 * pay_type：支付宝=43（订单号前缀 YW）、微信=44（前缀 WW）
 * 异步通知：验签优先用下单时存储的原始参数（最可靠），幂等落账 shop_payment
 *
 * sys_params 配置键：
 *   pay.xddpay.appId        — XDDPay 后台分配的应用 ID（整数）
 *   pay.xddpay.secret       — 通信密钥（签名计算用）
 *   pay.xddpay.notifyUrl    — 异步通知地址（同时需填到 XDDPay 商户后台）
 */
@Service
public class XddpayService {

    private static final Logger log = LoggerFactory.getLogger(XddpayService.class);

    static final String GATEWAY_URL = "https://gateway.xddpay.com";
    static final int PAY_TYPE_ALIPAY = 43;
    static final int PAY_TYPE_WECHAT = 44;

    private final ShopPaymentMapper paymentMapper;
    private final OrderMapper orderMapper;
    private final yuhe.modules.sys.dao.SysParamsDao sysParamsDao;

    public XddpayService(ShopPaymentMapper paymentMapper, OrderMapper orderMapper, SysParamsDao sysParamsDao) {
        this.paymentMapper = paymentMapper;
        this.orderMapper = orderMapper;
        this.sysParamsDao = sysParamsDao;
    }

    // ==================== 创建支付参数 ====================

    /** 支付渠道可用性（游客 /shop/pay/channels 用）：appId 与 secret 齐备即视为已配置 */
    public boolean isConfigured() {
        return param("pay.xddpay.appId") != null && param("pay.xddpay.secret") != null;
    }

    /**
     * 生成 XDDPay 支付参数（前端拿去动态建表单 POST 到网关）。
     * 返回 { gatewayUrl, orderNo, money, params:{order_no,subject,pay_type,money,app_id,extra,sign} }；
     * 未配置返回 { errorCode: PAY_NOT_CONFIGURED }。
     */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> createPayment(String orderId, String channel) {
        Map<String, Object> order = orderMapper.getById(orderId, null);
        if (order == null) {
            throw new IllegalArgumentException("订单不存在");
        }
        String appIdStr = param("pay.xddpay.appId");
        String secret = param("pay.xddpay.secret");
        if (appIdStr == null || secret == null) {
            log.warn("[xddpay] 配置未就绪（pay.xddpay.appId/secret 缺），orderId={}", orderId);
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("errorCode", "PAY_NOT_CONFIGURED");
            return r;
        }
        long appId;
        try {
            appId = Long.parseLong(appIdStr.trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("XDDPay App ID 必须为整数");
        }
        int payType = "wechat".equals(channel) ? PAY_TYPE_WECHAT : PAY_TYPE_ALIPAY;
        String prefix = payType == PAY_TYPE_WECHAT ? "WW" : "YW";

        // 商户订单号：前缀+日期+订单哈希+随机（商城同款结构，保证唯一）
        String orderNo = prefix + new java.text.SimpleDateFormat("yyMMdd").format(new java.util.Date())
                + String.format("%06d", Math.abs(orderId.hashCode()) % 1000000)
                + String.format("%03d", new java.util.Random().nextInt(1000));

        // 商品摘要：product 汇总截 50 字
        String subject = String.valueOf(order.get("product") == null ? "屿禾商店订单" : order.get("product"));
        if (subject.length() > 50) {
            subject = subject.substring(0, 47) + "...";
        }
        BigDecimal amount = order.get("amount") == null ? BigDecimal.ZERO
                : new BigDecimal(String.valueOf(order.get("amount")));
        String money = amount.setScale(2, java.math.RoundingMode.HALF_UP).toPlainString();

        String sign = makeSign(orderNo, subject, payType, money, appId, orderId, secret);

        Map<String, Object> p = new LinkedHashMap<>();
        p.put("order_no", orderNo);
        p.put("subject", subject);
        p.put("pay_type", String.valueOf(payType));
        p.put("money", money);
        p.put("app_id", String.valueOf(appId));
        p.put("extra", orderId);
        p.put("sign", sign);

        // 落流水（channel 区分 xddpay-alipay / xddpay-wechat；原始参数存 notify_raw 供验签兜底）
        paymentMapper.insertXddpay(orderNo, orderId,
                order.get("user_id") == null ? null : Long.valueOf(String.valueOf(order.get("user_id"))),
                amount, "xddpay-" + (payType == PAY_TYPE_WECHAT ? "wechat" : "alipay"), JsonUtils.toJsonString(p));

        Map<String, Object> r = new LinkedHashMap<>();
        r.put("gatewayUrl", GATEWAY_URL);
        r.put("orderNo", orderNo);
        r.put("money", money);
        r.put("params", p);
        return r;
    }

    // ==================== 异步通知 ====================

    /**
     * XDDPay 异步通知：验签（优先流水存储的原始参数）→ 金额校验 → 幂等落账。
     * 返回纯文本 "success" / "fail: xxx"（网关只认 success 停止重试）。
     */
    @Transactional(rollbackFor = Exception.class)
    public String handleNotify(Map<String, String> params) {
        try {
            String orderNo = firstNonNull(params.get("order_no"), params.get("out_trade_no"), params.get("mch_order_no"));
            if (orderNo == null || orderNo.isEmpty()) {
                log.warn("[xddpay] 通知缺少 order_no");
                return "fail: no order_no";
            }
            Map<String, Object> p = paymentMapper.getByOutTradeNo(orderNo);
            if (p == null) {
                log.warn("[xddpay] 流水不存在 order_no={}", orderNo);
                return "fail: payment not found";
            }
            String secret = param("pay.xddpay.secret");
            if (secret == null) {
                log.warn("[xddpay] secret 未配置，拒绝通知");
                return "fail: not configured";
            }
            String signReceived = params.get("sign") == null ? "" : params.get("sign").trim().toUpperCase();
            if (signReceived.isEmpty()) {
                return "fail: no sign";
            }

            String orderId = String.valueOf(p.get("order_id"));
            // 验签策略一（最可靠）：用流水里存储的原始参数重算
            boolean ok = false;
            try {
                Map<String, Object> stored = JsonUtils.parseMap(String.valueOf(p.get("notify_raw")));
                if (stored != null && stored.get("order_no") != null) {
                    String expect = makeSign(
                            String.valueOf(stored.get("order_no")),
                            String.valueOf(stored.get("subject")),
                            Integer.parseInt(String.valueOf(stored.get("pay_type"))),
                            String.valueOf(stored.get("money")),
                            Long.parseLong(String.valueOf(stored.get("app_id"))),
                            String.valueOf(stored.get("extra")), secret);
                    ok = expect.equals(signReceived);
                }
            } catch (Exception ignore) { /* 落到策略二 */ }

            // 验签策略二：用通知回传参数组装（网关回传完整时可用）
            if (!ok) {
                long appId = Long.parseLong(param("pay.xddpay.appId"));
                String expect = makeSign(orderNo,
                        params.get("subject") == null ? "" : params.get("subject"),
                        params.get("pay_type") == null ? 0 : Integer.parseInt(params.get("pay_type")),
                        params.get("money") == null ? "" : params.get("money"),
                        params.get("app_id") == null ? appId : Long.parseLong(params.get("app_id")),
                        params.get("extra") == null ? orderId : params.get("extra"), secret);
                ok = expect.equals(signReceived);
            }
            if (!ok) {
                log.warn("[xddpay] 验签失败 order_no={}", orderNo);
                return "fail: sign error";
            }

            // 金额校验（网关回传 money 与流水金额一致才落账）
            if (params.get("money") != null) {
                BigDecimal notified = new BigDecimal(params.get("money"));
                BigDecimal stored = new BigDecimal(String.valueOf(p.get("amount")));
                if (notified.compareTo(stored) != 0) {
                    log.warn("[xddpay] 金额不符 notified={} stored={}", params.get("money"), p.get("amount"));
                    return "fail: amount mismatch";
                }
            }

            String tradeNo = firstNonNull(params.get("trade_no"), params.get("transaction_id"), params.get("trade_id"));
            // markPaid 仅当 status=0 时置 1（幂等，重复通知天然安全）
            int rows = paymentMapper.markPaid(orderNo, tradeNo,
                    params.get("buyer_id"), params.get("gmt_payment"), JsonUtils.toJsonString(params));
            if (rows == 1) {
                orderMapper.markPaidTime(orderId);
                log.info("[xddpay] 支付成功落账 orderNo={} orderId={} tradeNo={}", orderNo, orderId, tradeNo);
            } else {
                log.info("[xddpay] 重复通知（已落账），orderNo={}", orderNo);
            }
            return "success";
        } catch (Exception e) {
            log.error("[xddpay] 通知处理异常", e);
            return "fail: internal error";
        }
    }

    // ==================== 工具 ====================

    /**
     * XDDPay 签名（1:1 商城规范）：
     * MD5("order_no={}&subject={}&pay_type={}&money={}&app_id={}&extra={}&{secret}") 转大写
     */
    static String makeSign(String orderNo, String subject, int payType, String money, long appId,
            String extra, String secret) {
        String raw = "order_no=" + orderNo
                + "&subject=" + subject
                + "&pay_type=" + payType
                + "&money=" + money
                + "&app_id=" + appId
                + "&extra=" + extra
                + "&" + secret;
        return md5Upper(raw);
    }

    static String md5Upper(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString().toUpperCase();
        } catch (Exception e) {
            throw new IllegalStateException("MD5 unavailable", e);
        }
    }

    private static String firstNonNull(String... vals) {
        for (String v : vals) {
            if (v != null && !v.isEmpty()) {
                return v;
            }
        }
        return null;
    }

    private String param(String code) {
        try {
            String v = sysParamsDao.getValueByCode(code);
            return v == null || v.trim().isEmpty() ? null : v.trim();
        } catch (Exception e) {
            return null;
        }
    }
}
