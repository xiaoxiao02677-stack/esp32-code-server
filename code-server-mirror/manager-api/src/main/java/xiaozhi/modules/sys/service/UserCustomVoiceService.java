package xiaozhi.modules.sys.service;

import java.util.List;
import java.util.Map;

import xiaozhi.modules.sys.entity.SysUserCustomVoiceEntity;

/**
 * 用户自定义音色
 */
public interface UserCustomVoiceService {

    /** 本人列表 */
    List<Map<String, Object>> myList(Long userId, Integer auditStatus);

    /** 新建（同名查重 10236） */
    void create(Long userId, Map<String, Object> body);

    /** 更新（仅本人） */
    void update(Long userId, String id, Map<String, Object> body);

    /** 删除（仅本人，非本人 10235） */
    void delete(Long userId, String id);

    /** 管理端分页 */
    Map<String, Object> adminPage(Integer auditStatus, String keyword, long page, long limit);

    /** 审核 */
    void audit(String id, boolean pass, String remark);

    /** 资源聚合用：本人审核通过的自定义音色（转资源条目） */
    List<Map<String, Object>> listApprovedAsResources(Long userId);

    /** 内部：按 ID 查实体 */
    SysUserCustomVoiceEntity getById(String id);
}
