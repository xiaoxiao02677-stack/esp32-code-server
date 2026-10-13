package xiaozhi.modules.sys.service;

import java.util.List;
import java.util.Map;

import xiaozhi.modules.sys.entity.SysUserCustomModelEntity;

/**
 * 用户自定义模型
 */
public interface UserCustomModelService {

    /** 本人列表（apiKey 永远掩码） */
    List<Map<String, Object>> myList(Long userId, String modelType, Integer auditStatus);

    /** 新建（同型同名查重 10234；apiKey AES 加密落 api_key_cipher） */
    void create(Long userId, Map<String, Object> body);

    /** 更新（仅本人；apiKey 空串/不传=不改） */
    void update(Long userId, String id, Map<String, Object> body);

    /** 删除（仅本人，非本人 10233） */
    void delete(Long userId, String id);

    /** 健康检查：对 baseUrl HTTP GET(10s)，返回 {status, latencyMs} */
    Map<String, Object> health(Long userId, String id);

    /** 管理端分页（auditStatus/modelType/keyword） */
    Map<String, Object> adminPage(Integer auditStatus, String modelType, String keyword, long page, long limit);

    /** 审核（通过→1，驳回→2；记审计） */
    void audit(String id, boolean pass, String remark);

    /** 配额设置 */
    void setQuota(String id, Integer quotaLimit);

    /** 资源聚合用：本人审核通过的自定义模型（转资源条目） */
    List<Map<String, Object>> listApprovedAsResources(Long userId, String modelType);

    /** 内部：按 ID 查实体 */
    SysUserCustomModelEntity getById(String id);
}
