package xiaozhi.modules.sys.service;

import java.util.List;
import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.sys.dto.SysRoleDTO;
import xiaozhi.modules.sys.entity.SysRoleEntity;
import xiaozhi.modules.sys.vo.SysRoleVO;

/**
 * 角色
 */
public interface SysRoleService extends BaseService<SysRoleEntity> {

    /** 分页（keyword 模糊匹配 role_code/role_name） */
    PageData<SysRoleVO> page(Map<String, Object> params);

    /** 启用角色下拉列表 [{id,roleCode,roleName}] */
    List<SysRoleVO> listEnabled();

    /** 详情（404 → 10228） */
    SysRoleVO get(Long id);

    /** 新增（roleCode 查重 10226；保留码校验） */
    void save(SysRoleDTO dto);

    /** 修改（内置角色仅允许改 permissions/remark） */
    void update(SysRoleDTO dto);

    /** 删除（内置 10227；先清 sys_user_role 关联） */
    void delete(Long[] ids);

    /** 查用户全部角色编码（含停用角色，Realm 鉴权用，status 过滤在调用方） */
    List<String> getRoleCodesByUserId(Long userId);

    /** 查用户全部角色ID */
    List<Long> getRoleIdsByUserId(Long userId);

    /** 查用户全部角色实体（status=1） */
    List<SysRoleEntity> getEnabledRolesByUserId(Long userId);

    /** 按 ID 批量查角色实体（含停用） */
    List<SysRoleEntity> getRolesByIds(List<Long> roleIds);

    /** 给用户分配角色（全删全插） */
    void assignUserRoles(Long userId, List<Long> roleIds);
}
