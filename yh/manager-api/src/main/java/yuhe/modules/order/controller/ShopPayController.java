package yuhe.modules.order.controller;

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
import yuhe.modules.order.service.ShopPayService;
import yuhe.modules.security.user.SecurityUser;

/**
 * 电商小店-支付预留端点（支付宝）。
 * /pay/create、/pay/status 走登录态（oauth2 兜底拦截，按用户校验订单归属）；
 * /pay/alipay/notify 是支付宝服务器回调，无 token，ShiroConfig 已 anon 放行。
 */
@RestController
@RequestMapping("/pay")
public class ShopPayController {

    private final ShopPayService shopPayService;

    public ShopPayController(ShopPayService shopPayService) {
        this.shopPayService = shopPayService;
    }

    /**
     * 创建支付（登录态）：body = { orderId }。
     * 配置齐全返回 { outTradeNo, payForm }——payForm 为完整表单 HTML，
     * 前端 document.write / 注入 body 即可跳转支付宝收银台；
     * 密钥未配返回 { outTradeNo, errorCode: "PAY_NOT_CONFIGURED" }（前端提示"支付暂未开通"）。
     */
    @PostMapping("/create")
    public Result<Map<String, Object>> create(@RequestBody Map<String, Object> body) {
        String orderId = body.get("orderId") == null ? null : String.valueOf(body.get("orderId")).trim();
        try {
            return new Result<Map<String, Object>>()
                    .ok(shopPayService.createAlipayPayment(SecurityUser.getUserId(), orderId));
        } catch (IllegalArgumentException e) {
            return new Result<Map<String, Object>>().error(e.getMessage());
        }
    }

    /** 支付状态轮询（登录态，前端下单后/回跳后轮询）：{ status: -1无流水 0待支付 1已支付 2已关闭, tradeNo?, outTradeNo? } */
    @GetMapping("/status/{orderId}")
    public Result<Map<String, Object>> status(@PathVariable String orderId) {
        return new Result<Map<String, Object>>().ok(shopPayService.paymentStatus(orderId.trim()));
    }

    /**
     * 支付宝异步通知（核心预留端点）。
     * 契约：POST form-urlencoded，无登录态；应答必须是纯文本 success（支付宝停止重试）/ fail（继续重试），
     * 绝不能走 Result JSON 包装（支付宝只认 7 字符 success）。
     * 服务内完成：RSA2 验签 → app_id/金额校验 → markPaid 幂等落账。
     */
    @PostMapping("/alipay/notify")
    public ResponseEntity<String> alipayNotify(@RequestParam Map<String, String> params) {
        String answer = shopPayService.handleAlipayNotify(params);
        return ResponseEntity.ok()
                .contentType(new MediaType(MediaType.TEXT_PLAIN, java.nio.charset.StandardCharsets.UTF_8))
                .body(answer);
    }
}
