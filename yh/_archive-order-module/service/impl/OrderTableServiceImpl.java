package yuhe.modules.order.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.service.impl.BaseServiceImpl;
import yuhe.common.utils.ConvertUtils;
import yuhe.modules.order.dao.OrderTableDao;
import yuhe.modules.order.dto.OrderTableDTO;
import yuhe.modules.order.entity.OrderTableEntity;
import yuhe.modules.order.service.OrderTableService;
import yuhe.modules.order.vo.OrderTableVO;
import yuhe.modules.sys.dao.SysUserDao;
import yuhe.modules.sys.entity.SysUserEntity;

/**
 * 订单服务实现
 */
@Service
@AllArgsConstructor
public class OrderTableServiceImpl extends BaseServiceImpl<OrderTableDao, OrderTableEntity>
        implements OrderTableService {

    private final SysUserDao sysUserDao;

    @Override
    public PageData<OrderTableVO> page(Map<String, Object> params) {
        paramsToLike(params, "keyword");
        IPage<OrderTableEntity> page = baseDao.selectPage(getPage(params, Constant.ID, false), getWrapper(params));
        List<OrderTableVO> voList = ConvertUtils.sourceToTarget(page.getRecords(), OrderTableVO.class);
        fillExtra(voList);
        return new PageData<>(voList, page.getTotal());
    }

    @Override
    public OrderTableVO get(Long id) {
        OrderTableEntity entity = baseDao.selectById(id);
        if (entity == null) {
            throw new RenException(10241);
        }
        OrderTableVO vo = ConvertUtils.sourceToTarget(entity, OrderTableVO.class);
        fillExtra(List.of(vo));
        return vo;
    }

    @Override
    public void save(OrderTableDTO dto) {
        OrderTableEntity entity = ConvertUtils.sourceToTarget(dto, OrderTableEntity.class);
        if (entity.getShippingStatus() == null) {
            entity.setShippingStatus(0);
        }
        insert(entity);
    }

    @Override
    public void update(OrderTableDTO dto) {
        OrderTableEntity exists = baseDao.selectById(dto.getId());
        if (exists == null) {
            throw new RenException(10241);
        }
        OrderTableEntity entity = ConvertUtils.sourceToTarget(dto, OrderTableEntity.class);
        updateById(entity);
    }

    @Override
    public void delete(Long id) {
        OrderTableEntity entity = baseDao.selectById(id);
        if (entity == null) {
            throw new RenException(10241);
        }
        entity.setDeleted(1);
        entity.setUpdateTime(new Date());
        baseDao.updateById(entity);
    }

    @Override
    public void deleteBatch(Long[] ids) {
        for (Long id : ids) {
            delete(id);
        }
    }

    @Override
    public List<String[]> exportRows(Map<String, Object> params) {
        QueryWrapper<OrderTableEntity> wrapper = getWrapper(params);
        List<OrderTableEntity> list = baseDao.selectList(wrapper);
        List<String[]> rows = new ArrayList<>();
        rows.add(new String[]{"用户姓名", "联系方式", "商品描述", "金额", "支付时间", "收货地址", "发货状态", "备注"});
        for (OrderTableEntity entity : list) {
            rows.add(new String[]{
                    entity.getUserName() == null ? "" : entity.getUserName(),
                    entity.getContact() == null ? "" : entity.getContact(),
                    entity.getProduct() == null ? "" : entity.getProduct(),
                    entity.getAmount() == null ? "" : entity.getAmount().toString(),
                    entity.getPayTime() == null ? "" : entity.getPayTime().toString(),
                    entity.getAddress() == null ? "" : entity.getAddress(),
                    getShippingStatusText(entity.getShippingStatus()),
                    entity.getRemark() == null ? "" : entity.getRemark()
            });
        }
        return rows;
    }

    @Override
    public Map<String, Object> getStats(Map<String, Object> params) {
        Date startDate = params.get("startDate") != null ? parseDate(params.get("startDate").toString()) : null;
        Date endDate = params.get("endDate") != null ? parseDate(params.get("endDate").toString()) : null;

        LambdaQueryWrapper<OrderTableEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(OrderTableEntity::getDeleted, 0);
        if (startDate != null) {
            wrapper.ge(OrderTableEntity::getPayTime, startDate);
        }
        if (endDate != null) {
            wrapper.le(OrderTableEntity::getPayTime, endDate);
        }

        long totalOrders = baseDao.selectCount(wrapper);
        Map<String, Object> result = baseDao.selectStats();
        if (result == null || result.isEmpty()) {
            result = Map.of("totalOrders", totalOrders, "totalAmount", 0);
        } else {
            result.put("totalOrders", totalOrders);
        }
        return result;
    }

    private QueryWrapper<OrderTableEntity> getWrapper(Map<String, Object> params) {
        String keyword = (String) params.get("keyword");
        Integer shippingStatus = params.get("shippingStatus") != null
                ? Integer.parseInt(params.get("shippingStatus").toString()) : null;
        Date startDate = params.get("startDate") != null ? parseDate(params.get("startDate").toString()) : null;
        Date endDate = params.get("endDate") != null ? parseDate(params.get("endDate").toString()) : null;

        QueryWrapper<OrderTableEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("deleted", 0);
        if (StringUtils.isNotBlank(keyword)) {
            wrapper.and(w -> w.like("user_name", keyword).or().like("contact", keyword).or().like("product", keyword));
        }
        if (shippingStatus != null) {
            wrapper.eq("shipping_status", shippingStatus);
        }
        if (startDate != null) {
            wrapper.ge("pay_time", startDate);
        }
        if (endDate != null) {
            wrapper.le("pay_time", endDate);
        }
        return wrapper;
    }

    private void fillExtra(List<OrderTableVO> voList) {
        if (voList == null || voList.isEmpty()) {
            return;
        }
        List<Long> userIds = voList.stream()
                .map(OrderTableVO::getCreator)
                .filter(id -> id != null)
                .distinct()
                .collect(Collectors.toList());
        if (!userIds.isEmpty()) {
            List<SysUserEntity> users = sysUserDao.selectByIds(userIds);
            Map<Long, String> userNameMap = users.stream()
                    .collect(Collectors.toMap(SysUserEntity::getId, SysUserEntity::getUsername, (a, b) -> a));
            voList.forEach(vo -> vo.setCreatorName(userNameMap.get(vo.getCreator())));
        }
    }

    private Date parseDate(String dateStr) {
        try {
            return new java.text.SimpleDateFormat("yyyy-MM-dd").parse(dateStr);
        } catch (Exception e) {
            return null;
        }
    }

    private String getShippingStatusText(Integer status) {
        if (status == null) {
            return "待发货";
        }
        switch (status) {
            case 0: return "待发货";
            case 1: return "已发货";
            case 2: return "已签收";
            case 3: return "已取消";
            default: return "未知";
        }
    }
}
