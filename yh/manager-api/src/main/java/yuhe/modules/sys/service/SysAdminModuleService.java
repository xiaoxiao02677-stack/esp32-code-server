package yuhe.modules.sys.service;

import java.util.List;
import java.util.Map;

import yuhe.common.page.PageData;
import yuhe.modules.sys.dto.AdminCustomAuditDTO;
import yuhe.modules.sys.dto.AdminCustomQuotaDTO;
import yuhe.modules.sys.dto.SysDisplayConfigSaveDTO;
import yuhe.modules.sys.dto.SysRoleSaveDTO;
import yuhe.modules.sys.dto.SysUserDefaultSaveDTO;
import yuhe.modules.sys.vo.AdminAuditLogVO;
import yuhe.modules.sys.vo.AdminCustomModelVO;
import yuhe.modules.sys.vo.AdminCustomVoiceVO;
import yuhe.modules.sys.vo.AdminRoleVO;

/**
 * 管理端扩展模块：角色管理 / 审计日志 / 展示配置 / 默认配置 / 自定义审核
 * （console-v2 五个页面的后端契约实现，SPEC §4.1/4.3/4.4/4.5）
 */
public interface SysAdminModuleService {

    // ===== 角色（SPEC §4.1） =====
    PageData<AdminRoleVO> rolePage(Map<String, Object> params);

    AdminRoleVO roleDetail(Long id);

    void roleSave(SysRoleSaveDTO dto);

    void roleUpdate(SysRoleSaveDTO dto);

    void roleDelete(List<Long> ids);

    // ===== 审计日志（SPEC §4.5） =====
    PageData<AdminAuditLogVO> auditPage(Map<String, Object> params);

    List<String> auditModules();

    // ===== 展示配置（SPEC §4.3） =====
    Map<String, Object> displayConfigGet(Integer scopeType, Long roleId, Long userId);

    void displayConfigSave(SysDisplayConfigSaveDTO dto);

    /**
     * 当前登录用户的生效展示配置（登录用户视角）：
     * 用户作用域 > 角色作用域 > 系统作用域逐层 merge（fields 键级覆盖）；
     * 前端顾客端/管理端用它过滤导航模块。无任何配置时返回空 fields/modules。
     */
    Map<String, Object> myDisplayConfig();

    /**
     * 指定用户的生效展示配置（Realm 授权/后台任务用，非登录上下文）。
     * 合并规则与 myDisplayConfig 一致。
     */
    Map<String, Object> mergedDisplayConfig(Long userId);

    // ===== 默认配置（SPEC §4.3） =====
    Map<String, Object> userDefaultGet(Integer scopeType, Long roleId, Long userId);

    void userDefaultSave(SysUserDefaultSaveDTO dto);

    // ===== 自定义审核（SPEC §4.4） =====
    PageData<AdminCustomModelVO> customModelPage(Map<String, Object> params);

    void customModelAudit(AdminCustomAuditDTO dto);

    void customModelQuota(AdminCustomQuotaDTO dto);

    PageData<AdminCustomVoiceVO> customVoicePage(Map<String, Object> params);

    void customVoiceAudit(AdminCustomAuditDTO dto);
}
