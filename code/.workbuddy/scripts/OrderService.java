package yuhe.modules.order.service;

import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import yuhe.common.page.PageData;
import yuhe.modules.order.dao.OrderMapper;

@Service
public class OrderService {
    
    private final OrderMapper orderMapper;
    
    public OrderService(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }
    
    public PageData page(int pageNum, int pageSize, String keyword) {
        int offset = (pageNum - 1) * pageSize;
        List<Map<String, Object>> list = orderMapper.selectList(keyword, offset, pageSize);
        int total = orderMapper.selectCount(keyword);
        
        return new PageData<>(list, total);
    }
    
    public Map<String, Object> getById(String id) {
        return orderMapper.getById(id);
    }
    
    public void create(Map<String, Object> params) {
        orderMapper.insert(params);
    }
    
    public void update(Map<String, Object> params) {
        orderMapper.update(params);
    }
    
    public void delete(String id) {
        orderMapper.delete(id);
    }
    
    public List<Map<String, Object>> export(String keyword) {
        return orderMapper.selectList(keyword, 0, 10000);
    }
}
