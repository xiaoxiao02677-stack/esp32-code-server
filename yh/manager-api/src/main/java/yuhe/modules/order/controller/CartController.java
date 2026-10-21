package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.order.service.OrderShopService;

/**
 * 电商小店-购物车 + 结算（按登录用户隔离；下单写 order_table，管理端零改动可发货）
 */
@RestController
@RequestMapping("/cart")
public class CartController {

    private final OrderShopService orderShopService;

    public CartController(OrderShopService orderShopService) {
        this.orderShopService = orderShopService;
    }

    @GetMapping("/list")
    public Result<List<Map<String, Object>>> list() {
        return new Result<List<Map<String, Object>>>().ok(orderShopService.cartList(SecurityUser.getUserId()));
    }

    @PostMapping("/add")
    public Result<Void> add(@RequestBody Map<String, Object> body) {
        Long goodsId = body.get("goodsId") == null ? null : Long.valueOf(String.valueOf(body.get("goodsId")));
        int qty = body.get("qty") == null ? 1 : Integer.parseInt(String.valueOf(body.get("qty")));
        orderShopService.cartAdd(SecurityUser.getUserId(), goodsId, qty);
        return new Result<Void>();
    }

    @PutMapping("/change/{id}")
    public Result<Void> change(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        int delta = body.get("delta") == null ? 1 : Integer.parseInt(String.valueOf(body.get("delta")));
        orderShopService.cartChange(SecurityUser.getUserId(), id, delta);
        return new Result<Void>();
    }

    @PutMapping("/qty/{id}")
    public Result<Void> setQty(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        int qty = body.get("qty") == null ? 1 : Integer.parseInt(String.valueOf(body.get("qty")));
        orderShopService.cartSetQty(SecurityUser.getUserId(), id, qty);
        return new Result<Void>();
    }

    @PutMapping("/checked/{id}")
    public Result<Void> checked(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        int checked = body.get("checked") == null ? 1 : Integer.parseInt(String.valueOf(body.get("checked")));
        orderShopService.cartChecked(SecurityUser.getUserId(), id, checked);
        return new Result<Void>();
    }

    @DeleteMapping("/delete/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        orderShopService.cartDelete(SecurityUser.getUserId(), id);
        return new Result<Void>();
    }

    /**
     * 结算下单：body = { userName, contact, shippingAddress, remark, cartIds?[] }。
     * cartIds 缺省 = 全部勾选行。成功返回 { orderId, amount, items }。
     */
    @PostMapping("/checkout")
    public Result<Map<String, Object>> checkout(@RequestBody Map<String, Object> body) {
        String userName = body.get("userName") == null ? null : String.valueOf(body.get("userName"));
        String contact = body.get("contact") == null ? null : String.valueOf(body.get("contact"));
        String address = body.get("shippingAddress") == null ? null : String.valueOf(body.get("shippingAddress"));
        String remark = body.get("remark") == null ? null : String.valueOf(body.get("remark"));
        List<Long> cartIds = null;
        Object raw = body.get("cartIds");
        if (raw instanceof List<?> l) {
            cartIds = l.stream()
                    .map(x -> Long.valueOf(String.valueOf(x)))
                    .collect(java.util.stream.Collectors.toList());
        }
        return new Result<Map<String, Object>>().ok(
                orderShopService.checkout(SecurityUser.getUserId(), userName, contact, address, remark, cartIds));
    }

    /** 我的订单分页（order_table.user_id 过滤；status: 0待发货 1已发货 2已完成 3已取消） */
    @GetMapping("/orders")
    public Result<PageData<Map<String, Object>>> myOrders(
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "1") Integer page,
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "10") Integer limit,
            @org.springframework.web.bind.annotation.RequestParam(required = false) String status) {
        return new Result<PageData<Map<String, Object>>>()
                .ok(orderShopService.myOrders(SecurityUser.getUserId(), page, limit, status));
    }
}
