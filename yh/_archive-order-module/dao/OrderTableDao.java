package yuhe.modules.order.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import yuhe.modules.order.entity.OrderTableEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Map;

/**
 * 订单表格DAO
 */
@Mapper
public interface OrderTableDao extends BaseMapper<OrderTableEntity> {

    /**
     * 分页查询订单列表
     */
    IPage<OrderTableEntity> selectPage(Page<OrderTableEntity> page,
                                       @Param("keyword") String keyword,
                                       @Param("sortBy") String sortBy,
                                       @Param("sortOrder") String sortOrder);

    /**
     * 查询统计数据
     */
    Map<String, Object> selectStats();
}
