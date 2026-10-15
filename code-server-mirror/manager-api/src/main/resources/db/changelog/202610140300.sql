-- ============================================================
-- 订单表格数据库建表脚本
-- 版本: 202610140300
-- 说明: 创建订单数据表，支持用户管理、联系方式、商品、金额、
--       支付时间、收货地址、发货状态、备注等字段
-- ============================================================

-- 订单表
CREATE TABLE IF NOT EXISTS `order_table` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键(UUID)',
  `user_name` VARCHAR(100) DEFAULT NULL COMMENT '用户姓名',
  `contact` VARCHAR(50) DEFAULT NULL COMMENT '联系方式',
  `product` TEXT DEFAULT NULL COMMENT '商品描述',
  `amount` DECIMAL(12,2) DEFAULT NULL COMMENT '金额（元）',
  `pay_time` DATETIME DEFAULT NULL COMMENT '支付时间',
  `address` VARCHAR(500) DEFAULT NULL COMMENT '收货地址',
  `shipping_status` VARCHAR(20) DEFAULT NULL COMMENT '发货状态',
  `remark` TEXT DEFAULT NULL COMMENT '备注',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_contact` (`contact`),
  KEY `idx_pay_time` (`pay_time`),
  KEY `idx_shipping_status` (`shipping_status`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表格数据';

-- 订单列配置表（存储自定义列配置）
CREATE TABLE IF NOT EXISTS `order_table_config` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键(UUID)',
  `config_key` VARCHAR(50) NOT NULL COMMENT '配置键名',
  `config_value` JSON DEFAULT NULL COMMENT '配置值(JSON格式)',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表格列配置';

-- 插入默认列配置
INSERT INTO `order_table_config` (`id`, `config_key`, `config_value`)
VALUES (
  'cfg_001',
  'default_columns',
  JSON_ARRAY(
    JSON_OBJECT('id', 'c_user', 'name', '用户', 'type', 'text', 'order', 1),
    JSON_OBJECT('id', 'c_contact', 'name', '联系方式', 'type', 'text', 'order', 2),
    JSON_OBJECT('id', 'c_product', 'name', '商品', 'type', 'text', 'order', 3),
    JSON_OBJECT('id', 'c_amount', 'name', '金额', 'type', 'number', 'order', 4),
    JSON_OBJECT('id', 'c_pay_time', 'name', '支付时间', 'type', 'datetime', 'order', 5),
    JSON_OBJECT('id', 'c_address', 'name', '收货地址', 'type', 'text', 'order', 6),
    JSON_OBJECT('id', 'c_shipping_status', 'name', '发货状态', 'type', 'text', 'order', 7),
    JSON_OBJECT('id', 'c_remark', 'name', '备注', 'type', 'text', 'order', 8)
  )
)
ON DUPLICATE KEY UPDATE `config_value` = VALUES(`config_value`);
