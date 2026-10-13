-- ============================================================
-- 背景：用户管理模块（sys_user 扩列）
-- 软删除/锁定/最后登录/强制改密/密码修改时间 6 列。
-- MySQL 无 ADD COLUMN IF NOT EXISTS，幂等由 master yaml 的
-- preConditions（not columnExists sys_user.deleted + MARK_RAN）保证。
-- ============================================================

ALTER TABLE `sys_user`
  ADD COLUMN `deleted`         TINYINT(1) NOT NULL DEFAULT '0' COMMENT '软删除（0否 1是）' AFTER `status`,
  ADD COLUMN `deleted_date`    DATETIME  DEFAULT NULL COMMENT '删除时间' AFTER `deleted`,
  ADD COLUMN `locked`          TINYINT(1) NOT NULL DEFAULT '0' COMMENT '锁定（0否 1是，锁定后禁止登录）' AFTER `deleted_date`,
  ADD COLUMN `last_login_date` DATETIME  DEFAULT NULL COMMENT '最后登录时间' AFTER `locked`,
  ADD COLUMN `must_change_pwd` TINYINT(1) NOT NULL DEFAULT '0' COMMENT '强制改密（0否 1是，管理员新建/重置后置1）' AFTER `last_login_date`,
  ADD COLUMN `pwd_update_date` DATETIME  DEFAULT NULL COMMENT '密码最后修改时间' AFTER `must_change_pwd`;
