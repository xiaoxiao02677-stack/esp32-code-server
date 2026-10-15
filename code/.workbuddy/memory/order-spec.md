# Order Table Module Design Spec

## Database Schema
```sql
CREATE TABLE IF NOT EXISTS `order_table` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键(UUID)',
  `user_name` VARCHAR(100) DEFAULT NULL COMMENT '用户姓名',
  `contact` VARCHAR(50) DEFAULT NULL COMMENT '联系方式',
  `product` TEXT DEFAULT NULL COMMENT '商品描述',
  `amount` DECIMAL(12,2) DEFAULT NULL COMMENT '金额',
  `pay_time` DATETIME DEFAULT NULL COMMENT '支付时间',
  `address` VARCHAR(500) DEFAULT NULL COMMENT '收货地址',
  `shipping_status` VARCHAR(20) DEFAULT NULL COMMENT '发货状态',
  `remark` TEXT DEFAULT NULL COMMENT '备注',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_pay_time` (`pay_time`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表格数据';
```

## API Endpoints
- GET /xiaozhi/order/page - 分页列表
- POST /xiaozhi/order - 新增订单
- PUT /xiaozhi/order/{id} - 更新订单
- DELETE /xiaozhi/order/{id} - 删除订单
- POST /xiaozhi/order/export - 导出CSV
- GET /xiaozhi/order/stats - 统计数据

## Column Config
- 存储在 `sys_params` 表中，key = 'order_table_columns'
- JSON格式: [{id, name, type, order}]
- 默认: ['用户', '联系方式', '商品', '金额', '支付时间', '收货地址', '发货状态', '备注']
