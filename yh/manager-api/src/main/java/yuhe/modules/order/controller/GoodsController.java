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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.order.service.OrderShopService;

/**
 * 电商小店-商品管理（照 OrderController 风格：Map 直传、无权限注解、登录即可）
 */
@RestController
@RequestMapping("/goods")
public class GoodsController {

    private final OrderShopService orderShopService;

    public GoodsController(OrderShopService orderShopService) {
        this.orderShopService = orderShopService;
    }

    @GetMapping("/page")
    public Result<PageData<Map<String, Object>>> page(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer limit,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) Integer status) {
        return new Result<PageData<Map<String, Object>>>()
                .ok(orderShopService.goodsPage(page, limit, keyword, category, status));
    }

    @GetMapping("/info/{id}")
    public Result<Map<String, Object>> info(@PathVariable Long id) {
        return new Result<Map<String, Object>>().ok(orderShopService.goodsInfo(id));
    }

    @PostMapping("/create")
    public Result<Long> create(@RequestBody Map<String, Object> params) {
        return new Result<Long>().ok(orderShopService.goodsCreate(params));
    }

    @PutMapping("/update/{id}")
    public Result<Long> update(@PathVariable Long id, @RequestBody Map<String, Object> params) {
        orderShopService.goodsUpdate(id, params);
        return new Result<Long>().ok(id);
    }

    @DeleteMapping("/delete/{id}")
    public Result<Long> delete(@PathVariable Long id) {
        orderShopService.goodsDelete(id);
        return new Result<Long>().ok(id);
    }

    @GetMapping("/export")
    public Result<List<Map<String, Object>>> export() {
        return new Result<List<Map<String, Object>>>().ok(orderShopService.goodsExport());
    }

    @PutMapping("/toggle/{id}")
    public Result<Long> toggle(@PathVariable Long id, @RequestParam(defaultValue = "1") Integer status) {
        orderShopService.goodsToggle(id, status);
        return new Result<Long>().ok(id);
    }

    // ===== 顾客端 =====

    @GetMapping("/on-sale")
    public Result<List<Map<String, Object>>> onSale() {
        return new Result<List<Map<String, Object>>>().ok(orderShopService.goodsOnSale());
    }

    @GetMapping("/categories")
    public Result<List<String>> categories() {
        return new Result<List<String>>().ok(orderShopService.goodsCategories());
    }
}
