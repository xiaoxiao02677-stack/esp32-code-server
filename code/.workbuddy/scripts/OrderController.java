package xiaozhi.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.*;

import xiaozhi.common.page.PageData;
import xiaozhi.modules.order.service.OrderService;

@RestController
@RequestMapping("/xiaozhi/order")
public class OrderController {
    
    private final OrderService orderService;
    
    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
    
    @GetMapping("/page")
    public PageData page(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer limit,
            @RequestParam(required = false) String keyword) {
        return orderService.page(page, limit, keyword);
    }
    
    @GetMapping("/info/{id}")
    public Map<String, Object> info(@PathVariable String id) {
        return orderService.getById(id);
    }
    
    @PostMapping("/create")
    public void create(@RequestBody Map<String, Object> params) {
        orderService.create(params);
    }
    
    @PutMapping("/update")
    public void update(@RequestBody Map<String, Object> params) {
        orderService.update(params);
    }
    
    @DeleteMapping("/delete/{id}")
    public void delete(@PathVariable String id) {
        orderService.delete(id);
    }
    
    @GetMapping("/export")
    public List<Map<String, Object>> export(
            @RequestParam(required = false) String keyword) {
        return orderService.export(keyword);
    }
}
