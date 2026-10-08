import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

/**
 * 获取认证token
 */
function getAuthToken() {
  return localStorage.getItem('token') || '';
}

/**
 * 通用API请求包装器
 * @param {Object} config - 请求配置
 * @param {string} config.url - 请求URL
 * @param {string} config.method - 请求方法
 * @param {Object} [config.data] - 请求数据
 * @param {Object} [config.headers] - 额外请求头
 * @param {Function} config.callback - 成功回调
 * @param {Function} [config.errorCallback] - 错误回调
 * @param {string} [config.errorMessage] - 错误消息
 * @param {Function} [config.retryFunction] - 重试函数
 */
function makeApiRequest(config) {
  const token = getAuthToken();
  const { url, method, data, headers, callback, errorCallback, errorMessage, retryFunction } = config;

  const requestBuilder = RequestService.sendRequest()
    .url(url)
    .method(method)
    .header({
      'Authorization': `Bearer ${token}`,
      ...headers
    });

  if (data) {
    requestBuilder.data(data);
  }

  requestBuilder
    .success((res) => {
      RequestService.clearRequestTime();
      callback(res);
    })
    .fail((err) => {
      console.error(errorMessage || '操作失败', err);
      if (errorCallback) {
        errorCallback(err);
      }
    })
    .networkFail(() => {
      if (retryFunction) {
        RequestService.reAjaxFun(() => {
          retryFunction();
        });
      }
    }).send();
}

/**
 * 记忆管理相关API（对齐设计文档 §3.2 /memory/** REST 规格）
 */
export default {
  /**
   * 获取有记忆数据的 Agent 列表
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  getMemoryAgents(callback, errorCallback) {
    makeApiRequest({
      url: `${getServiceUrl()}/memory/agents`,
      method: 'GET',
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '获取记忆Agent列表失败',
      retryFunction: () => this.getMemoryAgents(callback, errorCallback)
    });
  },

  /**
   * 获取记忆条目分页列表
   * @param {Object} params - 查询参数
   * @param {string} params.agent_id - Agent ID（必填）
   * @param {string} [params.keyword] - 关键词（FTS 命中内容与标签）
   * @param {string} [params.category] - 类型：preference/profile/habit/event/general
   * @param {string} [params.status] - 状态：active/rejected（不传=全部）
   * @param {number} [params.trust_min] - 信任分下限 0~1
   * @param {number} [params.trust_max] - 信任分上限 0~1
   * @param {string} [params.start] - 创建时间起（yyyy-MM-dd）
   * @param {string} [params.end] - 创建时间止（yyyy-MM-dd）
   * @param {number} [params.page=1] - 页码，从 1 起
   * @param {number} [params.size=20] - 每页条数，默认 20 上限 100
   * @param {string} [params.sort_by] - 排序字段：trust|created（默认 created）
   * @param {string} [params.order] - 排序方向：asc|desc（默认 desc）
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  getFactList(params, callback, errorCallback) {
    const query = {
      agent_id: params.agent_id,
      page: params.page || 1,
      size: params.size || 20
    };
    if (params.keyword) query.keyword = params.keyword;
    if (params.category) query.category = params.category;
    if (params.status) query.status = params.status;
    if (params.trust_min !== undefined && params.trust_min !== null && params.trust_min !== '') query.trust_min = params.trust_min;
    if (params.trust_max !== undefined && params.trust_max !== null && params.trust_max !== '') query.trust_max = params.trust_max;
    if (params.start) query.start = params.start;
    if (params.end) query.end = params.end;
    if (params.sort_by) query.sort_by = params.sort_by;
    if (params.order) query.order = params.order;

    const queryParams = new URLSearchParams(query).toString();
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts?${queryParams}`,
      method: 'GET',
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '获取记忆列表失败',
      retryFunction: () => this.getFactList(params, callback, errorCallback)
    });
  },

  /**
   * 获取记忆条目详情（含实体列表）
   * @param {number|string} factId - 条目ID
   * @param {string} agentId - Agent ID
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  getFactDetail(factId, agentId, callback, errorCallback) {
    const queryParams = new URLSearchParams({ agent_id: agentId }).toString();
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts/${factId}?${queryParams}`,
      method: 'GET',
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '获取记忆详情失败',
      retryFunction: () => this.getFactDetail(factId, agentId, callback, errorCallback)
    });
  },

  /**
   * 新增记忆条目
   * @param {Object} data - { agent_id*, content*, category?, tags?, trust_score? }
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  createFact(data, callback, errorCallback) {
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts`,
      method: 'POST',
      data: data,
      headers: { 'Content-Type': 'application/json' },
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '新增记忆失败',
      retryFunction: () => this.createFact(data, callback, errorCallback)
    });
  },

  /**
   * 编辑记忆条目（内容变更触发实体重抽取）
   * @param {number|string} factId - 条目ID
   * @param {Object} data - { agent_id*, content?, category?, tags?, trust_score? }
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  updateFact(factId, data, callback, errorCallback) {
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts/${factId}`,
      method: 'PUT',
      data: data,
      headers: { 'Content-Type': 'application/json' },
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '更新记忆失败',
      retryFunction: () => this.updateFact(factId, data, callback, errorCallback)
    });
  },

  /**
   * 删除记忆条目（物理删除，不可恢复）
   * @param {number|string} factId - 条目ID
   * @param {string} agentId - Agent ID
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  deleteFact(factId, agentId, callback, errorCallback) {
    const queryParams = new URLSearchParams({ agent_id: agentId }).toString();
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts/${factId}?${queryParams}`,
      method: 'DELETE',
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '删除记忆失败',
      retryFunction: () => this.deleteFact(factId, agentId, callback, errorCallback)
    });
  },

  /**
   * 信任分人工反馈（有用 +0.05 / 无用 -0.10）
   * @param {number|string} factId - 条目ID
   * @param {string} agentId - Agent ID
   * @param {boolean} helpful - true=有用 / false=无用
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  sendFeedback(factId, agentId, helpful, callback, errorCallback) {
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts/${factId}/feedback`,
      method: 'POST',
      data: { agent_id: agentId, helpful: helpful },
      headers: { 'Content-Type': 'application/json' },
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '反馈失败',
      retryFunction: () => this.sendFeedback(factId, agentId, helpful, callback, errorCallback)
    });
  },

  /**
   * 审核操作（P1：approve=通过 / reject=驳回）
   * @param {number|string} factId - 条目ID
   * @param {string} agentId - Agent ID
   * @param {string} action - "approve" | "reject"
   * @param {Function} callback - 成功回调
   * @param {Function} errorCallback - 错误回调
   */
  reviewFact(factId, agentId, action, callback, errorCallback) {
    makeApiRequest({
      url: `${getServiceUrl()}/memory/facts/${factId}/review`,
      method: 'POST',
      data: { agent_id: agentId, action: action },
      headers: { 'Content-Type': 'application/json' },
      callback: callback,
      errorCallback: errorCallback,
      errorMessage: '审核操作失败',
      retryFunction: () => this.reviewFact(factId, agentId, action, callback, errorCallback)
    });
  }
};
