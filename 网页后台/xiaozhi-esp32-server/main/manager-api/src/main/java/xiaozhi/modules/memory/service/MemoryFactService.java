package xiaozhi.modules.memory.service;

import java.util.List;

import xiaozhi.common.page.PageData;
import xiaozhi.modules.memory.dto.MemoryFactDTO;
import xiaozhi.modules.memory.vo.FeedbackVO;
import xiaozhi.modules.memory.vo.MemoryAgentVO;

/**
 * 记忆条目管理服务：按 Agent 绑定的记忆引擎分派
 * （mem_holographic→xiaozhi-server 内部 API 代理；mem0ai→平台只读；mem_local_short→引导提示；nomem/mem_report_only→空列表）
 */
public interface MemoryFactService {

    /**
     * 查询当前用户有权限访问、且有记忆数据的智能体列表
     *
     * @param userId 当前用户ID
     * @return 智能体列表（含引擎与条目统计）
     */
    List<MemoryAgentVO> listAgents(Long userId);

    /**
     * 分页查询记忆条目（sortBy: created/trust；order: asc/desc）
     */
    PageData<MemoryFactDTO> getFactPage(String agentId, String keyword, String category, String status,
            Double trustMin, Double trustMax, String start, String end, Integer page, Integer size,
            String sortBy, String order, Long userId);

    /**
     * 查询记忆条目详情（含实体列表）
     */
    MemoryFactDTO getFact(String agentId, Long factId, Long userId);

    /**
     * 新增记忆条目
     */
    MemoryFactDTO saveFact(MemoryFactDTO dto, Long userId);

    /**
     * 编辑记忆条目（内容变更时由服务端触发实体重抽取）
     */
    MemoryFactDTO updateFact(Long factId, MemoryFactDTO dto, Long userId);

    /**
     * 删除记忆条目（物理删除，不可恢复）
     */
    void deleteFact(String agentId, Long factId, Long userId);

    /**
     * 信任分反馈（有用+0.05 / 无用-0.10，钳制[0,1]）
     */
    FeedbackVO feedback(String agentId, Long factId, Boolean helpful, Long userId);

    /**
     * 审核（approve→status=active且trust=0.5；reject→status=rejected）
     */
    MemoryFactDTO review(String agentId, Long factId, String action, Long userId);
}
