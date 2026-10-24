package yuhe.modules.order.service;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import yuhe.common.page.PageData;
import yuhe.common.user.UserDetail;
import yuhe.modules.order.dao.OrderMapper;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.enums.SuperAdminEnum;

@Service
public class OrderService {

    private final OrderMapper orderMapper;

    public OrderService(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }

    /**
     * 数据范围：超管返回 null（全量），普通用户返回本人 userId（强制过滤）。
     * /order/* 无 /admin 前缀，Shiro 只保证已登录，读接口必须在这里收敛数据范围。
     */
    private Long scopeUserId() {
        UserDetail user = SecurityUser.getUser();
        if (user == null || user.getId() == null) {
            return -1L;
        }
        if (user.getSuperAdmin() != null && user.getSuperAdmin() == SuperAdminEnum.YES.value()) {
            return null;
        }
        return user.getId();
    }

    public PageData page(int pageNum, int pageSize, String keyword) {
        if (pageNum < 1) {
            pageNum = 1;
        }
        if (pageSize < 1) {
            pageSize = 10;
        }
        int offset = (pageNum - 1) * pageSize;
        Long userId = scopeUserId();
        List<Map<String, Object>> list = orderMapper.selectList(keyword, userId, offset, pageSize);
        int total = orderMapper.selectCount(keyword, userId);
        return new PageData<>(list, total);
    }

    public Map<String, Object> getById(String id) {
        return orderMapper.getById(id, scopeUserId());
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
        return orderMapper.selectList(keyword, scopeUserId(), 0, 10000);
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
