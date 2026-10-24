package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.*;

import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.order.service.OrderService;

@RestController
@RequestMapping("/order")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/page")
    public Result<PageData<Map<String, Object>>> page(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer limit,
            @RequestParam(required = false) String keyword) {
        return new Result<PageData<Map<String, Object>>>().ok(orderService.page(page, limit, keyword));
    }

    @GetMapping("/info/{id}")
    public Result<Map<String, Object>> info(@PathVariable String id) {
        return new Result<Map<String, Object>>().ok(orderService.getById(id));
    }

    /**
     * 管理端订单 CRUD（/admin/Orders 页面专用）。/order/** 不在 /admin/** Shiro 拦截链下，
     * 只做登录校验：读接口在 Service 层按用户收敛数据范围，写接口必须超管。
     */
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:orders"}, logical = Logical.OR)
    @PostMapping("/create")
    public Result<String> create(@RequestBody Map<String, Object> params) {
        orderService.create(params);
        return new Result<String>().ok(String.valueOf(params.get("id")));
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:orders"}, logical = Logical.OR)
    @PutMapping("/update")
    public Result<String> update(@RequestBody Map<String, Object> params) {
        orderService.update(params);
        return new Result<String>().ok(String.valueOf(params.get("id")));
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:orders"}, logical = Logical.OR)
    @DeleteMapping("/delete/{id}")
    public Result<String> delete(@PathVariable String id) {
        orderService.delete(id);
        return new Result<String>().ok(id);
    }

    @GetMapping("/export")
    public Result<List<Map<String, Object>>> export(
            @RequestParam(required = false) String keyword) {
        return new Result<List<Map<String, Object>>>().ok(orderService.export(keyword));
    }
}
