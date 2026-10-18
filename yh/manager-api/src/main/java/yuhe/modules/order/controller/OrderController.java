package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

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

    @PostMapping("/create")
    public Result<String> create(@RequestBody Map<String, Object> params) {
        orderService.create(params);
        return new Result<String>().ok(String.valueOf(params.get("id")));
    }

    @PutMapping("/update")
    public Result<String> update(@RequestBody Map<String, Object> params) {
        orderService.update(params);
        return new Result<String>().ok(String.valueOf(params.get("id")));
    }

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
