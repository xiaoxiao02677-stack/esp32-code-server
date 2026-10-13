package xiaozhi.modules.sys.service;

import java.util.List;
import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.sys.dto.AdminPageUserDTO;
import xiaozhi.modules.sys.dto.AdminUserCreateDTO;
import xiaozhi.modules.sys.dto.PasswordDTO;
import xiaozhi.modules.sys.dto.SysUserDTO;
import xiaozhi.modules.sys.dto.UserImportDTO;
import xiaozhi.modules.sys.entity.SysUserEntity;
import xiaozhi.modules.sys.vo.AdminUserDetailVO;
import xiaozhi.modules.sys.vo.AdminUserPageVO;
import xiaozhi.modules.sys.vo.UserImportResultVO;
import xiaozhi.modules.sys.vo.UserSessionVO;

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

    // ==================== 用户管理模块扩展 ====================

    /**
     * 用户管理分页（keyword/deleted/roleId 过滤；含已删除用户）
     */
    PageData<AdminUserPageVO> pageUsers(Map<String, Object> params);

    /**
     * 管理员新建用户：密码缺省自动生成12位，mustChangePwd=1，可选分配角色
     *
     * @return 初始密码
     */
    String createUser(AdminUserCreateDTO dto);

    /**
     * 用户详情（含角色）
     */
    AdminUserDetailVO getUserDetail(Long id);

    /**
     * 软删除（deleted=1, deletedDate=now；已删抛 10222；不级联删设备/智能体）
     */
    void softDelete(Long id);

    /**
     * 恢复软删除用户
     */
    void restore(Long id);

    /**
     * 分配角色（防自改：不能修改自己的角色；防最后一个启用超管失去管理权）
     */
    void assignRoles(Long userId, List<Long> roleIds);

    /**
     * 批量导入（部分失败抛 10225 且 data 携带明细）
     */
    UserImportResultVO importUsers(List<UserImportDTO> list);

    /**
     * 导出 CSV 行（username,状态,角色,创建时间,最后登录）
     */
    List<String[]> exportRows(String keyword, Integer deleted);

    /**
     * 在线会话分页
     */
    PageData<UserSessionVO> pageSessions(Map<String, Object> params);

    /**
     * 强制下线某用户（过期其全部 token）
     */
    void forceLogout(Long userId);

    /**
     * 登录成功后更新（lastLoginDate=now）
     */
    void updateLastLogin(Long userId);

    /**
     * 修改自己密码成功后清 mustChangePwd、写 pwdUpdateDate
     */
    void clearMustChangePwd(Long userId);

    /**
     * 查用户角色编码列表（登录响应附加信息用）
     */
    List<String> getUserRoleCodes(Long userId);
}
