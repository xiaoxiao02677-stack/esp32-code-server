package yuhe.modules.agent.service;

import yuhe.common.page.PageData;
import yuhe.common.service.BaseService;
import yuhe.modules.agent.dto.AgentSnapshotPageDTO;
import yuhe.modules.agent.entity.AgentSnapshotEntity;
import yuhe.modules.agent.vo.AgentSnapshotVO;

public interface AgentSnapshotService extends BaseService<AgentSnapshotEntity> {
    void createSnapshot(String agentId, String source);

    PageData<AgentSnapshotVO> page(String agentId, AgentSnapshotPageDTO params);

    AgentSnapshotVO getSnapshot(String agentId, String snapshotId);

    void restoreSnapshot(String agentId, String snapshotId, String currentStateToken);

    void deleteSnapshot(String agentId, String snapshotId);

    Integer getCurrentVersionNo(String agentId);

    void deleteByAgentId(String agentId);

    long redactLegacySnapshots();
}
