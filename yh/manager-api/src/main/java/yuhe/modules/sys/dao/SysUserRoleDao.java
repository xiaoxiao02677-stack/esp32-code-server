package yuhe.modules.sys.dao;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import yuhe.modules.sys.entity.SysUserRoleEntity;

/**
 * 用户-角色关联
 */
@Mapper
public interface SysUserRoleDao extends BaseMapper<SysUserRoleEntity> {

    @Select("SELECT role_id FROM sys_user_role WHERE user_id = #{userId}")
    java.util.List<Long> selectRoleIdsByUserId(@Param("userId") Long userId);

    /** 用户角色码（登录态 UserDetail.roles 数据源；连表 sys_role 过滤已删除角色） */
    @Select("SELECT r.role_code FROM sys_user_role ur JOIN sys_role r ON r.id = ur.role_id"
            + " WHERE ur.user_id = #{userId}")
    java.util.List<String> selectRoleCodesByUserId(@Param("userId") Long userId);

    @Delete("DELETE FROM sys_user_role WHERE user_id = #{userId}")
    int deleteByUserId(@Param("userId") Long userId);
}
