package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.dao.SysUserCustomVoiceDao;
import xiaozhi.modules.sys.entity.SysUserCustomVoiceEntity;
import xiaozhi.modules.sys.service.AuditService;
import xiaozhi.modules.sys.service.UserCustomVoiceService;

/**
 * 用户自定义音色实现（审核后可用）
 */
@Service
@AllArgsConstructor
public class UserCustomVoiceServiceImpl implements UserCustomVoiceService {

    private final SysUserCustomVoiceDao sysUserCustomVoiceDao;
    private final AuditService auditService;

    @Override
    public List<Map<String, Object>> myList(Long userId, Integer auditStatus) {
        LambdaQueryWrapper<SysUserCustomVoiceEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserCustomVoiceEntity::getUserId, userId);
        wrapper.eq(auditStatus != null, SysUserCustomVoiceEntity::getAuditStatus, auditStatus);
        wrapper.orderByDesc(SysUserCustomVoiceEntity::getCreateDate);

        List<Map<String, Object>> result = new ArrayList<>();
        for (SysUserCustomVoiceEntity e : sysUserCustomVoiceDao.selectList(wrapper)) {
            result.add(toVo(e));
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(Long userId, Map<String, Object> body) {
        String name = str(body, "name");
        if (StringUtils.isBlank(name)) {
            throw new RenException(ErrorCode.NOT_NULL);
        }

        // 同名查重（10236）
        LambdaQueryWrapper<SysUserCustomVoiceEntity> dupWrapper = new LambdaQueryWrapper<>();
        dupWrapper.eq(SysUserCustomVoiceEntity::getUserId, userId);
        dupWrapper.eq(SysUserCustomVoiceEntity::getName, name);
        if (sysUserCustomVoiceDao.selectCount(dupWrapper) > 0) {
            throw new RenException(ErrorCode.CUSTOM_VOICE_DUPLICATE);
        }

        SysUserCustomVoiceEntity entity = new SysUserCustomVoiceEntity();
        entity.setId(UUID.randomUUID().toString().replace("-", ""));
        entity.setUserId(userId);
        entity.setName(name);
        entity.setTtsModelId(str(body, "ttsModelId"));
        entity.setTtsVoice(str(body, "ttsVoice"));
        entity.setLanguages(str(body, "languages"));
        entity.setReferenceAudio(str(body, "referenceAudio"));
        entity.setReferenceText(str(body, "referenceText"));
        entity.setAuditStatus(0);
        entity.setStatus(1);
        entity.setRemark(str(body, "remark"));
        entity.setSort(0);

        sysUserCustomVoiceDao.insert(entity);
        auditService.log("custom", "create", "custom_voice", entity.getId(), body, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(Long userId, String id, Map<String, Object> body) {
        SysUserCustomVoiceEntity entity = requireOwned(userId, id);

        if (body.containsKey("name")) {
            String name = str(body, "name");
            if (StringUtils.isNotBlank(name) && !name.equals(entity.getName())) {
                LambdaQueryWrapper<SysUserCustomVoiceEntity> dupWrapper = new LambdaQueryWrapper<>();
                dupWrapper.eq(SysUserCustomVoiceEntity::getUserId, userId);
                dupWrapper.eq(SysUserCustomVoiceEntity::getName, name);
                dupWrapper.ne(SysUserCustomVoiceEntity::getId, id);
                if (sysUserCustomVoiceDao.selectCount(dupWrapper) > 0) {
                    throw new RenException(ErrorCode.CUSTOM_VOICE_DUPLICATE);
                }
                entity.setName(name);
            }
        }
        if (body.containsKey("ttsModelId")) {
            entity.setTtsModelId(str(body, "ttsModelId"));
        }
        if (body.containsKey("ttsVoice")) {
            entity.setTtsVoice(str(body, "ttsVoice"));
        }
        if (body.containsKey("languages")) {
            entity.setLanguages(str(body, "languages"));
        }
        if (body.containsKey("referenceAudio")) {
            entity.setReferenceAudio(str(body, "referenceAudio"));
        }
        if (body.containsKey("referenceText")) {
            entity.setReferenceText(str(body, "referenceText"));
        }
        if (body.containsKey("remark")) {
            entity.setRemark(str(body, "remark"));
        }

        sysUserCustomVoiceDao.updateById(entity);
        auditService.log("custom", "update", "custom_voice", id, body, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String id) {
        requireOwned(userId, id);
        sysUserCustomVoiceDao.deleteById(id);
        auditService.log("custom", "delete", "custom_voice", id, null, true, null);
    }

    @Override
    public Map<String, Object> adminPage(Integer auditStatus, String keyword, long page, long limit) {
        LambdaQueryWrapper<SysUserCustomVoiceEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(auditStatus != null, SysUserCustomVoiceEntity::getAuditStatus, auditStatus);
        wrapper.like(StringUtils.isNotBlank(keyword), SysUserCustomVoiceEntity::getName, keyword);
        wrapper.orderByDesc(SysUserCustomVoiceEntity::getCreateDate);

        Page<SysUserCustomVoiceEntity> pager = new Page<>(page, limit);
        Page<SysUserCustomVoiceEntity> result = sysUserCustomVoiceDao.selectPage(pager, wrapper);

        List<Map<String, Object>> list = new ArrayList<>();
        for (SysUserCustomVoiceEntity e : result.getRecords()) {
            list.add(toVo(e));
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("list", list);
        data.put("total", result.getTotal());
        return data;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void audit(String id, boolean pass, String remark) {
        SysUserCustomVoiceEntity entity = getById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.CUSTOM_VOICE_NOT_FOUND);
        }

        SysUserCustomVoiceEntity patch = new SysUserCustomVoiceEntity();
        patch.setId(id);
        patch.setAuditStatus(pass ? 1 : 2);
        patch.setAuditRemark(remark);
        patch.setAuditor(SecurityUser.getUserId());
        patch.setAuditDate(new Date());
        sysUserCustomVoiceDao.updateById(patch);

        auditService.log("custom", "audit", "custom_voice", id,
                Map.of("pass", pass, "remark", remark == null ? "" : remark), true, null);
    }

    @Override
    public List<Map<String, Object>> listApprovedAsResources(Long userId) {
        if (userId == null) {
            return new ArrayList<>();
        }
        LambdaQueryWrapper<SysUserCustomVoiceEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserCustomVoiceEntity::getUserId, userId);
        wrapper.eq(SysUserCustomVoiceEntity::getAuditStatus, 1);
        wrapper.eq(SysUserCustomVoiceEntity::getStatus, 1);
        wrapper.orderByAsc(SysUserCustomVoiceEntity::getSort);

        List<Map<String, Object>> result = new ArrayList<>();
        for (SysUserCustomVoiceEntity e : sysUserCustomVoiceDao.selectList(wrapper)) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", e.getId());
            item.put("name", e.getName());
            item.put("ttsModelId", e.getTtsModelId());
            item.put("source", "custom");
            result.add(item);
        }
        return result;
    }

    @Override
    public SysUserCustomVoiceEntity getById(String id) {
        return sysUserCustomVoiceDao.selectById(id);
    }

    // ==================== 私有工具 ====================

    private SysUserCustomVoiceEntity requireOwned(Long userId, String id) {
        SysUserCustomVoiceEntity entity = sysUserCustomVoiceDao.selectById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.CUSTOM_VOICE_NOT_FOUND);
        }
        if (!entity.getUserId().equals(userId)) {
            throw new RenException(ErrorCode.CUSTOM_VOICE_NOT_FOUND);
        }
        return entity;
    }

    private Map<String, Object> toVo(SysUserCustomVoiceEntity e) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", e.getId());
        vo.put("userId", e.getUserId());
        vo.put("name", e.getName());
        vo.put("ttsModelId", e.getTtsModelId());
        vo.put("ttsVoice", e.getTtsVoice());
        vo.put("languages", e.getLanguages());
        vo.put("referenceAudio", e.getReferenceAudio());
        vo.put("referenceText", e.getReferenceText());
        vo.put("auditStatus", e.getAuditStatus());
        vo.put("auditRemark", e.getAuditRemark());
        vo.put("status", e.getStatus());
        vo.put("remark", e.getRemark());
        vo.put("createDate", e.getCreateDate());
        return vo;
    }

    private String str(Map<String, Object> body, String key) {
        Object v = body.get(key);
        return v == null ? null : String.valueOf(v);
    }
}
