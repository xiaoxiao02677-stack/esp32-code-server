package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import yuhe.common.utils.Result;
import yuhe.modules.order.service.OrderShopService;
import yuhe.modules.order.service.ShopPayService;
import yuhe.modules.order.service.XddpayService;

/**
 * 独立商店（免登录游客通道）。
 * 前置：/goods/on-sale、/goods/categories 已在 ShiroConfig anon 放行（商店无需登录即可浏览）。
 * 本控制器只承担"下单/查单/支付"三个写敏感操作，凭订单号即可访问，语义与商城 yuhe.pro 一致：
 * 未登录 → 填收货信息 → 直接下单支付。
 */
@RestController
@RequestMapping("/shop")
public class GuestShopController {

    private final OrderShopService orderShopService;
    private final ShopPayService shopPayService;
    private final XddpayService xddpayService;

    public GuestShopController(OrderShopService orderShopService, ShopPayService shopPayService,
            XddpayService xddpayService) {
        this.orderShopService = orderShopService;
        this.shopPayService = shopPayService;
        this.xddpayService = xddpayService;
    }

    /**
     * 游客直购下单：body = { userName, contact, shippingAddress, remark, items: [{goodsId, qty}] }。
     * 成功返回 { orderId, amount, items }。
     */
    @PostMapping("/checkout")
    public Result<Map<String, Object>> checkout(@RequestBody Map<String, Object> body) {
        String userName = body.get("userName") == null ? null : String.valueOf(body.get("userName"));
        String contact = body.get("contact") == null ? null : String.valueOf(body.get("contact"));
        String address = body.get("shippingAddress") == null ? null : String.valueOf(body.get("shippingAddress"));
        String remark = body.get("remark") == null ? null : String.valueOf(body.get("remark"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> items = body.get("items") instanceof List<?> l
                ? (List<Map<String, Object>>) l
                : null;
        return new Result<Map<String, Object>>().ok(
                orderShopService.guestCheckout(userName, contact, address, remark, items));
    }

    /** 游客订单查询（凭订单号）：返回 order_table 整行 + payStatus（0待支付 1已支付） */
    @GetMapping("/order/{orderId}")
    public Result<Map<String, Object>> order(@PathVariable String orderId) {
        Map<String, Object> o = orderShopService.guestOrder(orderId.trim());
        Map<String, Object> pay = shopPayService.paymentStatus(orderId.trim());
        o.put("payStatus", pay.get("status"));
        o.put("payOutTradeNo", pay.get("outTradeNo"));
        return new Result<Map<String, Object>>().ok(o);
    }

    /**
     * 支付渠道可用性（游客，无需下单即可探测）：{ xddpay: {alipay,wechat}, alipay: {direct} }。
     * 前端据此渲染支付按钮——未配置的渠道不展示，避免点进去才发现"支付暂未开通"。
     */
    @GetMapping("/pay/channels")
    public Result<Map<String, Object>> payChannels() {
        Map<String, Object> r = new java.util.LinkedHashMap<>();
        boolean xddpay = xddpayService.isConfigured();
        Map<String, Object> x = new java.util.LinkedHashMap<>();
        x.put("alipay", xddpay);
        x.put("wechat", xddpay);
        r.put("xddpay", x);
        r.put("alipayDirect", shopPayService.isAlipayConfigured());
        return new Result<Map<String, Object>>().ok(r);
    }

    /**
     * 游客支付创建（凭订单号）：body = { orderId }。
     * 返回结构同登录版 /pay/create：{ outTradeNo, payForm? } 或 { outTradeNo, errorCode: PAY_NOT_CONFIGURED }。
     */
    @PostMapping("/pay")
    public Result<Map<String, Object>> pay(@RequestBody Map<String, Object> body) {
        String orderId = body.get("orderId") == null ? null : String.valueOf(body.get("orderId")).trim();
        return new Result<Map<String, Object>>().ok(shopPayService.createAlipayPayment(null, orderId));
    }

    /**
     * 游客支付创建（XDDPay 小多支付，1:1 复刻商城 yy-personal-pay）：body = { orderId, channel }。
     * channel: "alipay"(默认) / "wechat"。
     * 返回 { gatewayUrl, orderNo, money, params:{order_no,subject,pay_type,money,app_id,extra,sign} }，
     * 前端动态建表单 POST 到 gatewayUrl（对应商城中转页 submitPayForm 行为）；
     * 未配置返回 { errorCode: PAY_NOT_CONFIGURED }。
     */
    @PostMapping("/pay/xddpay")
    public Result<Map<String, Object>> payXddpay(@RequestBody Map<String, Object> body) {
        String orderId = body.get("orderId") == null ? null : String.valueOf(body.get("orderId")).trim();
        String channel = body.get("channel") == null ? "alipay" : String.valueOf(body.get("channel"));
        try {
            return new Result<Map<String, Object>>().ok(xddpayService.createPayment(orderId, channel));
        } catch (IllegalArgumentException e) {
            return new Result<Map<String, Object>>().error(e.getMessage());
        }
    }

    /**
     * XDDPay 异步通知（网关服务器回调，无登录态）。
     * 契约：POST form-urlencoded；应答必须是纯文本 success（网关停止重试）/ fail: xxx（继续重试），
     * 绝不能走 Result JSON 包装——与 /pay/alipay/notify 同一模式。
     * 服务内完成：验签（原始参数优先）→ 金额校验 → markPaid 幂等落账。
     * 路径在 /shop/** 内，ShiroConfig 已 anon 放行，无需改白名单。
     */
    @PostMapping("/pay/xddpay/notify")
    public ResponseEntity<String> xddpayNotify(@RequestParam Map<String, String> params) {
        String answer = xddpayService.handleNotify(params);
        return ResponseEntity.ok()
                .contentType(new MediaType(MediaType.TEXT_PLAIN, java.nio.charset.StandardCharsets.UTF_8))
                .body(answer);
    }
}
