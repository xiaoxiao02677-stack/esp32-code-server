-- 订单表格建表脚本
CREATE TABLE IF NOT EXISTS `order_table` (
  `id` VARCHAR(32) NOT NULL,
  `user_name` VARCHAR(100) DEFAULT NULL,
  `contact` VARCHAR(50) DEFAULT NULL,
  `product` TEXT DEFAULT NULL,
  `amount` DECIMAL(12,2) DEFAULT NULL,
  `pay_time` DATETIME DEFAULT NULL,
  `address` VARCHAR(500) DEFAULT NULL,
  `shipping_status` VARCHAR(20) DEFAULT NULL,
  `remark` TEXT DEFAULT NULL,
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_pay_time` (`pay_time`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表格数据';

CREATE TABLE IF NOT EXISTS `order_table_config` (
  `id` VARCHAR(32) NOT NULL,
  `config_key` VARCHAR(50) NOT NULL,
  `config_value` JSON DEFAULT NULL,
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表格列配置';
