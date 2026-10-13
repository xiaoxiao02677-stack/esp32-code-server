package xiaozhi.modules.sys.dao;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import xiaozhi.common.dao.BaseDao;
import xiaozhi.modules.sys.entity.SysUserEntity;
import xiaozhi.modules.sys.vo.UserSessionVO;

/**
 * 系统用户
 */
@Mapper
public interface SysUserDao extends BaseDao<SysUserEntity> {

    /** 全量查询（绕过 @TableLogic，含已软删用户） */
    List<SysUserEntity> selectAllIncludeDeleted(@Param("keyword") String keyword, @Param("deleted") Integer deleted);

    /** 按 ID 查（含已软删用户） */
    SysUserEntity getByIdIncludeDeleted(@Param("id") Long id);

    /** 统计（含已软删用户） */
    long countIncludeDeleted(@Param("deleted") Integer deleted);

    /** 统计启用的超级管理员（软删/停用不计） */
    long countEnabledSuperAdmin();

    /** 软删除 */
    int softDelete(@Param("id") Long id);

    /** 恢复软删除 */
    int restore(@Param("id") Long id);

    /** 最后登录时间 */
    int updateLastLogin(@Param("userId") Long userId);

    /** 清除强制改密标记 */
    int clearMustChangePwd(@Param("userId") Long userId);

    /** 在线会话分页（调用方手动分页） */
    List<UserSessionVO> selectSessions(@Param("keyword") String keyword);

    /** 强制下线：过期该用户全部 token */
    int expireUserTokens(@Param("userId") Long userId);
}
