package yuhe.modules.sys.service;

import yuhe.common.page.PageData;
import yuhe.common.service.BaseService;
import yuhe.modules.sys.dto.AdminPageUserDTO;
import yuhe.modules.sys.dto.PasswordDTO;
import yuhe.modules.sys.dto.SysUserDTO;
import yuhe.modules.sys.entity.SysUserEntity;
import yuhe.modules.sys.vo.AdminPageUserVO;

/**
 * 系统用户
 */
public interface SysUserService extends BaseService<SysUserEntity> {

    SysUserDTO getByUsername(String username);

    SysUserDTO getByUserId(Long userId);

    void save(SysUserDTO dto);

    /**
     * 删除指定用户，且有关联的数据设备和智能体
     * 
     * @param ids
     */
    void deleteById(Long ids);

    /**
     * 验证是否允许修改密码更改
     * 
     * @param userId      用户id
     * @param passwordDTO 验证密码的参数
     */
    void changePassword(Long userId, PasswordDTO passwordDTO);

    /**
     * 直接修改密码，不需要验证
     * 
     * @param userId   用户id
     * @param password 密码
     */
    void changePasswordDirectly(Long userId, String password);

    /**
     * 重置密码
     * 
     * @param userId 用户id
     * @return 随机生成符合规范的密码
     */
    String resetPassword(Long userId);

    /**
     * 管理员分页用户信息
     *
     * @param dto 分页查找参数
     * @return 用户列表分页数据
     */
    PageData<AdminPageUserVO> page(AdminPageUserDTO dto);

    /**
     * 管理端用户分页（console-v2 Users.vue：deleted 回收站过滤 + keyword 用户名搜索 +
     * roleNames 批量装配，返回 AdminUserListVO）
     */
    PageData<yuhe.modules.sys.vo.AdminUserListVO> adminPage(java.util.Map<String, Object> params);

    /**
     * 批量修改用户状态
     * 
     * @param status  用户状态
     * @param userIds 用户ID数组
     */
    void changeStatus(Integer status, String[] userIds);

    /**
     * 获取是否允许用户注册
     *
     * @return 是否允许用户注册
     */
    boolean getAllowUserRegister();

    /**
     * 管理端新增用户（用户名查重、密码缺省生成、可选角色绑定）
     *
     * @param dto 用户名/密码?/角色?
     * @return 初始密码（明文，仅此一次返回）
     */
    String adminCreate(yuhe.modules.sys.dto.AdminUserCreateDTO dto);

    /**
     * 管理端用户详情（user + 当前角色）
     */
    yuhe.modules.sys.vo.AdminUserDetailVO detail(Long userId);

    /**
     * 管理端分配角色（全量覆盖；清空时拒绝清掉最后一个超管的角色，防失锁）
     */
    void assignRoles(yuhe.modules.sys.dto.AdminUserRolesDTO dto);

    /**
     * 软删除（deleted=1；自己/最后一个超管拒绝）
     */
    void softDelete(Long userId, Long operatorId);

    /**
     * 从回收站恢复（deleted=0）
     */
    void restore(Long userId);

    /**
     * 批量导入（逐条查重；部分失败抛 10225 携带 {success,failed}）
     */
    java.util.Map<String, Object> importUsers(java.util.List<yuhe.modules.sys.dto.AdminUserImportItemDTO> list);

    /**
     * 在线会话分页（sys_user_token 未过期记录，按创建时间倒序）
     */
    yuhe.common.page.PageData<yuhe.modules.sys.vo.AdminSessionVO> pageSessions(java.util.Map<String, Object> params);

    /**
     * 强制下线（把该用户 token 过期时间置为过去，等价 logout）
     */
    void forceLogout(Long userId);

    /**
     * 角色列表（启用状态全部角色）
     */
    java.util.List<yuhe.modules.sys.entity.SysRoleEntity> listRoles();

    /**
     * 登录前账号三态校验（deleted/locked/status），不通过抛对应错误码
     */
    void assertLoginAllowed(Long userId);

    /**
     * 登录成功后更新最后登录时间
     */
    void touchLastLogin(Long userId);
}
