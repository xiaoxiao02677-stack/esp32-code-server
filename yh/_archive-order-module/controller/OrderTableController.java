package yuhe.modules.order.controller;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.common.validator.ValidatorUtils;
import yuhe.modules.order.dto.OrderTableDTO;
import yuhe.modules.order.service.OrderTableService;
import yuhe.modules.order.vo.OrderTableVO;

/**
 * 订单管理
 */
@AllArgsConstructor
@RestController
@RequestMapping("/yuhe/order")
@Tag(name = "订单管理")
public class OrderTableController {

    private final OrderTableService orderTableService;

    @GetMapping("/page")
    @Operation(summary = "分页查询订单")
    @RequiresPermissions("yuhe:order:list")
    @Parameters({
            @Parameter(name = "keyword", description = "搜索关键字（用户姓名/联系方式/商品）"),
            @Parameter(name = "shippingStatus", description = "发货状态：0-待发货 1-已发货 2-已签收 3-已取消"),
            @Parameter(name = "startDate", description = "开始时间（yyyy-MM-dd）"),
            @Parameter(name = "endDate", description = "结束时间（yyyy-MM-dd）"),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true)
    })
    public Result<PageData<OrderTableVO>> page(@Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<OrderTableVO> page = orderTableService.page(params);
        return new Result<PageData<OrderTableVO>>().ok(page);
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取订单详情")
    @RequiresPermissions("yuhe:order:list")
    public Result<OrderTableVO> get(@PathVariable("id") Long id) {
        OrderTableVO vo = orderTableService.get(id);
        return new Result<OrderTableVO>().ok(vo);
    }

    @PostMapping
    @Operation(summary = "新增订单")
    @RequiresPermissions("yuhe:order:add")
    public Result<Void> save(@RequestBody OrderTableDTO dto) {
        ValidatorUtils.validateEntity(dto);
        orderTableService.save(dto);
        return new Result<>();
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新订单")
    @RequiresPermissions("yuhe:order:update")
    public Result<Void> update(@PathVariable("id") Long id, @RequestBody OrderTableDTO dto) {
        dto.setId(id);
        ValidatorUtils.validateEntity(dto);
        orderTableService.update(dto);
        return new Result<>();
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除订单（软删）")
    @RequiresPermissions("yuhe:order:delete")
    public Result<Void> delete(@PathVariable("id") Long id) {
        orderTableService.delete(id);
        return new Result<>();
    }

    @PostMapping("/export")
    @Operation(summary = "导出订单CSV")
    @RequiresPermissions("yuhe:order:list")
    @Parameters({
            @Parameter(name = "keyword", description = "搜索关键字（用户姓名/联系方式/商品）"),
            @Parameter(name = "shippingStatus", description = "发货状态：0-待发货 1-已发货 2-已签收 3-已取消"),
            @Parameter(name = "startDate", description = "开始时间（yyyy-MM-dd）"),
            @Parameter(name = "endDate", description = "结束时间（yyyy-MM-dd）")
    })
    public void export(@RequestParam(required = false) String keyword,
                       @RequestParam(required = false) Integer shippingStatus,
                       @RequestParam(required = false) String startDate,
                       @RequestParam(required = false) String endDate,
                       HttpServletResponse response) throws IOException {
        Map<String, Object> params = new HashMap<>();
        if (keyword != null) {
            params.put("keyword", keyword);
        }
        if (shippingStatus != null) {
            params.put("shippingStatus", shippingStatus);
        }
        if (startDate != null) {
            params.put("startDate", startDate);
        }
        if (endDate != null) {
            params.put("endDate", endDate);
        }

        List<String[]> rows = orderTableService.exportRows(params);

        StringBuilder sb = new StringBuilder("\uFEFF");
        for (String[] row : rows) {
            for (int i = 0; i < row.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                String cell = row[i] == null ? "" : row[i].replace("\"", "\"\"");
                sb.append('"').append(cell).append('"');
            }
            sb.append("\r\n");
        }

        response.setContentType("text/csv; charset=UTF-8");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=" + URLEncoder.encode("orders.csv", StandardCharsets.UTF_8));
        response.getOutputStream().write(sb.toString().getBytes(StandardCharsets.UTF_8));
        response.getOutputStream().flush();
    }

    @GetMapping("/stats")
    @Operation(summary = "订单统计数据")
    @RequiresPermissions("yuhe:order:list")
    @Parameters({
            @Parameter(name = "startDate", description = "开始时间（yyyy-MM-dd）"),
            @Parameter(name = "endDate", description = "结束时间（yyyy-MM-dd）")
    })
    public Result<Map<String, Object>> stats(@RequestParam(required = false) String startDate,
                                              @RequestParam(required = false) String endDate) {
        Map<String, Object> params = new HashMap<>();
        if (startDate != null) {
            params.put("startDate", startDate);
        }
        if (endDate != null) {
            params.put("endDate", endDate);
        }
        Map<String, Object> result = orderTableService.getStats(params);
        return new Result<Map<String, Object>>().ok(result);
    }
}
