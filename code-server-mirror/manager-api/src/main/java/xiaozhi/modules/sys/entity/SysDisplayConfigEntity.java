package xiaozhi.modules.sys.entity;

import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.entity.BaseEntity;

/**
 * 展示项配置（系统→角色→用户三级覆盖）
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_display_config")
public class SysDisplayConfigEntity extends BaseEntity {
    /**
     * 作用域（0系统默认 1角色 2用户）
     */
    private Integer scopeType;
    /**
     * 角色ID（scope_type=1 时有效，其余填 0）
     */
    private Long roleId;
    /**
     * 用户ID（scope_type=2 时有效，其余填 0）
     */
    private Long userId;
    /**
     * 展示配置 JSON 原文：{"fields":{"llm_model":{"visible":true,"editable":false},...}}
     */
    private String configJson;
}
