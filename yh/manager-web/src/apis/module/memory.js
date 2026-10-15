import { get, post, del } from '@/apis/httpRequest'

const BASE_URL = '/xiaozhi/api/memory'

export const memoryApi = {
  // ==================== 实体图谱 ====================
  /**
   * 获取实体列表
   */
  getEntities(agentId) {
    return get(`${BASE_URL}/entities/${agentId}`)
  },

  /**
   * 获取实体图谱
   */
  getEntityGraph(agentId) {
    return get(`${BASE_URL}/entities/${agentId}/graph`)
  },

  /**
   * 从对话中提取实体
   */
  extractEntities(agentId, factId) {
    return post(`${BASE_URL}/entities/${agentId}/extract`, { fact_id: factId })
  },

  // ==================== 时间线 ====================
  /**
   * 获取时间线列表
   */
  getTimeline(agentId, limit = 50) {
    return get(`${BASE_URL}/timeline/${agentId}`, { limit })
  },

  /**
   * 获取时间线图表数据
   */
  getTimelineChart(agentId, days = 30) {
    return get(`${BASE_URL}/timeline/${agentId}/chart`, { days })
  },

  /**
   * 创庺时间线条目
   */
  createTimelineEntry(agentId, data) {
    return post(`${BASE_URL}/timeline/${agentId}`, data)
  },

  /**
   * 删除时间线条目
   */
  deleteTimelineEntry(agentId, entryId) {
    return del(`${BASE_URL}/timeline/${agentId}/${entryId}`)
  },

  // ==================== 推送调度 ====================
  /**
   * 获取推送调度列表
   */
  getPushSchedule() {
    return get(`${BASE_URL}/push/schedule`)
  },

  /**
   * 创庺推送任务
   */
  createPushSchedule(data) {
    return post(`${BASE_URL}/push/schedule`, data)
  },

  /**
   * 删除推送任务
   */
  deletePushSchedule(pushId) {
    return del(`${BASE_URL}/push/schedule/${pushId}`)
  },

  // ==================== 唤醒词管理 ====================
  /**
   * 获取唤醒词状态
   */
  getWakeWordStatus(agentId) {
    return get(`${BASE_URL}/wake-word/status`, { agent_id: agentId })
  },

  /**
   * 推送唤醒词配置
   */
  pushWakeWord(agentId, data) {
    return post(`${BASE_URL}/wake-word/push`, { agent_id: agentId, ...data })
  },

  // ==================== 微信绑定 ====================
  /**
   * 获取微信绑定状态
   */
  getWechatBindStatus(agentId) {
    return get(`${BASE_URL}/wechat/bind`, { agent_id: agentId })
  },

  /**
   * 绑定微信
   */
  bindWechat(agentId, data) {
    return post(`${BASE_URL}/wechat/bind`, { agent_id: agentId, ...data })
  },

  /**
   * 解绑微信
   */
  unbindWechat(agentId) {
    return del(`${BASE_URL}/wechat/bind/${agentId}`)
  }
}

export default memoryApi
