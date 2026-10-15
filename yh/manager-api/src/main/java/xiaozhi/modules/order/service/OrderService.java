package xiaozhi.modules.order.service;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import xiaozhi.common.page.PageData;
import xiaozhi.modules.order.dao.OrderMapper;

@Service
public class OrderService {

    private final OrderMapper orderMapper;

    public OrderService(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }

    public PageData page(int pageNum, int pageSize, String keyword) {
        if (pageNum < 1) {
            pageNum = 1;
        }
        if (pageSize < 1) {
            pageSize = 10;
        }
        int offset = (pageNum - 1) * pageSize;
        List<Map<String, Object>> list = orderMapper.selectList(keyword, offset, pageSize);
        int total = orderMapper.selectCount(keyword);
        return new PageData<>(list, total);
    }

    public Map<String, Object> getById(String id) {
        return orderMapper.getById(id);
    }

    public void create(Map<String, Object> params) {
        if (params == null) {
            return;
        }
        Object id = params.get("id");
        if (id == null || String.valueOf(id).trim().isEmpty()) {
            params.put("id", "OD" + UUID.randomUUID().toString().replace("-", "").substring(0, 20));
        }
        if (params.get("status") == null) {
            params.put("status", "0");
        }
        normalizeDateTime(params, "paymentTime");
        orderMapper.insert(params);
    }

    public void update(Map<String, Object> params) {
        if (params == null) {
            return;
        }
        Object id = params.get("id");
        if (id == null || String.valueOf(id).trim().isEmpty()) {
            throw new IllegalArgumentException("订单ID不能为空");
        }
        normalizeDateTime(params, "paymentTime");
        orderMapper.update(params);
    }

    public void delete(String id) {
        orderMapper.delete(id);
    }

    public List<Map<String, Object>> export(String keyword) {
        return orderMapper.selectList(keyword, 0, 10000);
    }

    /**
     * 前端传入的支付时间可能是 "2026-10-14T12:30" 这种 ISO 格式，
     * MySQL 的 datetime 列不能直接接收，统一转换成 "yyyy-MM-dd HH:mm:ss"。
     */
    private void normalizeDateTime(Map<String, Object> params, String key) {
        Object value = params.get(key);
        if (value == null) {
            return;
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            params.put(key, null);
            return;
        }
        text = text.replace("T", " ");
        if (text.length() == 16) {
            text = text + ":00";
        }
        params.put(key, text);
    }
}
