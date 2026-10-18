package yuhe.modules.order.service;

import java.util.List;
import java.util.Map;

import yuhe.common.page.PageData;
import yuhe.common.service.BaseService;
import yuhe.modules.order.dto.OrderTableDTO;
import yuhe.modules.order.entity.OrderTableEntity;
import yuhe.modules.order.vo.OrderTableVO;

/**
 * 订单服务
 */
public interface OrderTableService extends BaseService<OrderTableEntity> {

    /**
     * 分页查询订单列表
     */
    PageData<OrderTableVO> page(Map<String, Object> params);

    /**
     * 获取订单详情
     */
    OrderTableVO get(Long id);

    /**
     * 新增订单
     */
    void save(OrderTableDTO dto);

    /**
     * 修改订单
     */
    void update(OrderTableDTO dto);

    /**
     * 软删除订单
     */
    void delete(Long id);

    /**
     * 批量软删除订单
     */
    void deleteBatch(Long[] ids);

    /**
     * 导出订单CSV
     */
    List<String[]> exportRows(Map<String, Object> params);

    /**
     * 统计订单数据
     */
    Map<String, Object> getStats(Map<String, Object> params);
}
