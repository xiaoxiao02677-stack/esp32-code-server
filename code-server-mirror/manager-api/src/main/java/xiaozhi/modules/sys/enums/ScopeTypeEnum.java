package xiaozhi.modules.sys.enums;

/**
 * 用户管理模块公共枚举：作用域类型（展示配置/默认配置共用）。
 * scope 0=系统/平台 1=角色 2=用户。
 */
public enum ScopeTypeEnum {

    SYSTEM(0, "系统"),
    ROLE(1, "角色"),
    USER(2, "用户");

    private final int value;
    private final String label;

    ScopeTypeEnum(int value, String label) {
        this.value = value;
        this.label = label;
    }

    public int getValue() {
        return value;
    }

    public String getLabel() {
        return label;
    }

    /** 校验取值合法（0/1/2），非法抛 RenException(ErrorCode.DISPLAY_CONFIG_SCOPE) */
    public static ScopeTypeEnum of(int value) {
        for (ScopeTypeEnum t : values()) {
            if (t.value == value) {
                return t;
            }
        }
        throw new xiaozhi.common.exception.RenException(
                xiaozhi.common.exception.ErrorCode.DISPLAY_CONFIG_SCOPE);
    }
}
