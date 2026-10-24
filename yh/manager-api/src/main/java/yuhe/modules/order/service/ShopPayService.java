package yuhe.modules.order.service;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.alipay.api.AlipayApiException;
import com.alipay.api.AlipayClient;
import com.alipay.api.DefaultAlipayClient;
import com.alipay.api.internal.util.AlipaySignature;
import com.alipay.api.request.AlipayTradePagePayRequest;
import com.alipay.api.response.AlipayTradePagePayResponse;

import yuhe.common.utils.JsonUtils;
import yuhe.modules.order.controller.ShopPaymentMapper;
import yuhe.modules.order.dao.OrderMapper;

/**
 * 支付宝支付服务（预接入）。
 * 当前状态：回调端点 /pay/alipay/notify（Shiro anon）+ 流水表已就绪；
 * 沙箱密钥未配前 createAlipayPayment 返回明确的"未配置"提示（errorCode PAY_NOT_CONFIGURED），
 * 不吞错不伪造成功。密钥接入后把配置项填入 sys_params 即全链路可用。
 *
 * 待接配置项（sys_params 编码）：
 *   pay.alipay.appId        — 应用 APPID（沙箱 9021 开头）
 *   pay.alipay.privateKey   — 应用私钥（PKCS8，-----BEGIN PRIVATE KEY-----）
 *   pay.alipay.publicKey    — 支付宝公钥（验签用）
 *   pay.alipay.gateway      — 网关（沙箱 openapi-sandbox.dl.alipaydev.com / 正式 openapi.alipay.com）
 *   pay.alipay.notifyUrl    — 异步通知地址（https 公网可达，如 https://sandyun.top/yuhe/pay/alipay/notify）
 *   pay.alipay.returnUrl    — 同步跳转地址（直接配前端订单页，如 https://sandyun.top:8144/shop/orders；
 *                             前端回跳后轮询 GET /pay/status/{orderId} 取真实结果，后端无需 return 端点）
 */
@Service
public class ShopPayService {

    private static final Logger log = LoggerFactory.getLogger(ShopPayService.class);

    private final ShopPaymentMapper paymentMapper;
    private final OrderMapper orderMapper;
    private final yuhe.modules.sys.dao.SysParamsDao sysParamsDao;

    public ShopPayService(ShopPaymentMapper paymentMapper, OrderMapper orderMapper,
            yuhe.modules.sys.dao.SysParamsDao sysParamsDao) {
        this.paymentMapper = paymentMapper;
        this.orderMapper = orderMapper;
        this.sysParamsDao = sysParamsDao;
    }

    // ==================== 下单创建支付 ====================

    /**
     * 创建支付宝支付（PC 网页支付），返回 payment = { outTradeNo, payUrl?, payForm?, errorCode? }。
     * 密钥未配时 errorCode = "PAY_NOT_CONFIGURED"（前端据此提示"支付暂未开通"）。
     */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> createAlipayPayment(Long userId, String orderId) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("订单号不能为空");
        }
        // 校验订单存在且归属当前用户（归属判断在下方 Java 层做，这里 ownerId 传 null 不加 SQL 限制）
        Map<String, Object> order = orderMapper.getById(orderId.trim(), null);
        if (order == null) {
            throw new IllegalArgumentException("订单不存在");
        }
        Object uid = order.get("user_id");
        if (uid != null && userId != null && !String.valueOf(uid).equals(String.valueOf(userId))) {
            throw new IllegalArgumentException("无权支付该订单");
        }
        Object amountObj = order.get("amount");
        BigDecimal amount = amountObj == null ? BigDecimal.ZERO : new BigDecimal(String.valueOf(amountObj));
        String outTradeNo = "P" + System.currentTimeMillis() + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        paymentMapper.insert(outTradeNo, orderId.trim(), userId, amount);

        String appId = param("pay.alipay.appId");
        String privateKey = param("pay.alipay.privateKey");
        String gateway = param("pay.alipay.gateway");
        if (appId == null || privateKey == null || gateway == null) {
            log.warn("[alipay] 支付配置未就绪（appId/privateKey/gateway 缺），outTradeNo={} 仅落流水待支付", outTradeNo);
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("outTradeNo", outTradeNo);
            r.put("errorCode", "PAY_NOT_CONFIGURED");
            return r;
        }

        try {
            AlipayClient client = new DefaultAlipayClient(gateway, appId, privateKey,
                    "json", "UTF-8", param("pay.alipay.publicKey"), "RSA2");
            AlipayTradePagePayRequest request = new AlipayTradePagePayRequest();
            request.setNotifyUrl(param("pay.alipay.notifyUrl"));
            request.setReturnUrl(param("pay.alipay.returnUrl"));
            Map<String, Object> biz = new LinkedHashMap<>();
            biz.put("out_trade_no", outTradeNo);
            biz.put("total_amount", amount.setScale(2).toPlainString());
            biz.put("subject", String.valueOf(order.get("product") == null ? "屿禾商店订单" : order.get("product")));
            biz.put("product_code", "FAST_INSTANT_TRADE_PAY");
            request.setBizContent(JsonUtils.toJsonString(biz));
            AlipayTradePagePayResponse resp = client.pageExecute(request);
            if (resp.isSuccess()) {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("outTradeNo", outTradeNo);
                r.put("payForm", resp.getBody());
                return r;
            }
            log.warn("[alipay] pageExecute 失败 code={} msg={}", resp.getCode(), resp.getMsg());
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("outTradeNo", outTradeNo);
            r.put("errorCode", "PAY_CREATE_FAILED");
            r.put("errorMsg", resp.getSubMsg() != null ? resp.getSubMsg() : resp.getMsg());
            return r;
        } catch (AlipayApiException e) {
            log.error("[alipay] 创建支付异常", e);
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("outTradeNo", outTradeNo);
            r.put("errorCode", "PAY_CREATE_FAILED");
            r.put("errorMsg", e.getErrMsg());
            return r;
        }
    }

    /** 查询支付状态（前端轮询用）：返回 { status, tradeNo?, gmtPayment? } */
    public Map<String, Object> paymentStatus(String orderId) {
        Map<String, Object> p = paymentMapper.getLatestByOrder(orderId);
        Map<String, Object> r = new LinkedHashMap<>();
        if (p == null) {
            r.put("status", -1); // 无支付记录
            return r;
        }
        r.put("status", p.get("status"));
        r.put("tradeNo", p.get("trade_no"));
        r.put("gmtPayment", p.get("gmt_payment"));
        r.put("outTradeNo", p.get("out_trade_no"));
        return r;
    }

    // ==================== 支付宝异步通知（核心预留） ====================

    /**
     * 处理支付宝异步通知。
     * 验签 → 金额校验 → 落账（幂等）→ 订单置"已发货前置"（保持 status=0 待发货，
     * 但写入支付成功标记：order_table.shipping_status 语义为发货状态，支付完成不改变它；
     * 支付成功信息仅记录在 shop_payment 流水中，管理端后续加"支付状态"列时直接 join）。
     * 返回 "success" 告知支付宝停止重试。
     */
    @Transactional(rollbackFor = Exception.class)
    public String handleAlipayNotify(Map<String, String> params) {
        try {
            String publicKey = param("pay.alipay.publicKey");
            if (publicKey == null) {
                log.warn("[alipay] 验签公钥未配置，拒绝回调（防伪造）");
                return "fail";
            }
            boolean ok = AlipaySignature.rsaCheckV2(params, publicKey, "UTF-8", "RSA2");
            if (!ok) {
                log.warn("[alipay] 验签失败，拒绝回调 out_trade_no={}", params.get("out_trade_no"));
                return "fail";
            }
            String outTradeNo = params.get("out_trade_no");
            String tradeStatus = params.get("trade_status");
            String tradeNo = params.get("trade_no");
            String totalAmount = params.get("total_amount");
            String appId = params.get("app_id");
            String configuredAppId = param("pay.alipay.appId");
            if (configuredAppId != null && !configuredAppId.equals(appId)) {
                log.warn("[alipay] app_id 不匹配 {} != {}，拒绝", appId, configuredAppId);
                return "fail";
            }
            Map<String, Object> p = paymentMapper.getByOutTradeNo(outTradeNo);
            if (p == null) {
                log.warn("[alipay] 流水不存在 out_trade_no={}", outTradeNo);
                return "fail";
            }
            // 金额一致性校验（防篡改）
            if (totalAmount != null) {
                BigDecimal notified = new BigDecimal(totalAmount);
                BigDecimal stored = new BigDecimal(String.valueOf(p.get("amount")));
                if (notified.compareTo(stored) != 0) {
                    log.warn("[alipay] 金额不符 notified={} stored={}", totalAmount, p.get("amount"));
                    return "fail";
                }
            }
            if ("TRADE_SUCCESS".equals(tradeStatus) || "TRADE_FINISHED".equals(tradeStatus)) {
                // markPaid 带 status=0 条件，重复通知天然幂等
                int rows = paymentMapper.markPaid(outTradeNo, tradeNo, params.get("buyer_id"),
                        params.get("gmt_payment"), JsonUtils.toJsonString(params));
                if (rows == 1) {
                    log.info("[alipay] 支付成功落账 outTradeNo={} orderId={} tradeNo={}",
                            outTradeNo, p.get("order_id"), tradeNo);
                }
                return "success";
            }
            if ("TRADE_CLOSED".equals(tradeStatus)) {
                paymentMapper.closePendingByOrder(String.valueOf(p.get("order_id")));
                log.info("[alipay] 交易关闭 out_trade_no={}", outTradeNo);
                return "success";
            }
            // WAIT_BUYER_PAY 等中间态：应答 success 但不动流水
            log.info("[alipay] 中间态通知 {} out_trade_no={}", tradeStatus, outTradeNo);
            return "success";
        } catch (Exception e) {
            log.error("[alipay] 回调处理异常", e);
            return "fail";
        }
    }

    // ==================== 工具 ====================

    private String param(String code) {
        try {
            String v = sysParamsDao.getValueByCode(code);
            return v == null || v.trim().isEmpty() ? null : v.trim();
        } catch (Exception e) {
            return null;
        }
    }
}
