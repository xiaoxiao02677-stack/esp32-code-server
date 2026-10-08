import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';
import store from '@/store';

const CALLBACK_RETRY_LIMIT = 10;
const CALLBACK_RETRY_DELAY_MS = 2000;
const CALLBACK_RETRY_WINDOW_MS = CALLBACK_RETRY_LIMIT * CALLBACK_RETRY_DELAY_MS;

function retryCallbackRequest(retry, retryCount, onTerminalFailure, error, retryStartedAt) {
  if (!onTerminalFailure) {
    RequestService.reAjaxFun(() => retry(retryCount + 1));
    return;
  }
  const startedAt = retryStartedAt || Date.now();
  if (retryCount >= CALLBACK_RETRY_LIMIT || Date.now() - startedAt >= CALLBACK_RETRY_WINDOW_MS) {
    RequestService.clearRequestTime();
    if (onTerminalFailure) {
      onTerminalFailure(error);
    }
    return;
  }
  setTimeout(() => retry(retryCount + 1, startedAt), CALLBACK_RETRY_DELAY_MS);
}

export default {
  // 获取模型配置列表
  getModelList(params, callback) {
    const queryParams = new URLSearchParams({
      modelType: params.modelType,
      modelName: params.modelName || '',
      page: params.page || 0,
      limit: params.limit || 10
    }).toString();

    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/list?${queryParams}`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('获取模型列表失败:', err)
        RequestService.reAjaxFun(() => {
          this.getModelList(params, callback)
        })
      }).send()
  },
  // 获取模型供应器列表
  getModelProviders(modelType, callback, errorCallback) {
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${modelType}/provideTypes`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res.data?.data || [])
      })
      .networkFail((err) => {
        console.error('获取供应器列表失败:', err)
        RequestService.reAjaxFun(() => {
          this.getModelProviders(modelType, callback, errorCallback)
        })
      })
    if (errorCallback) {
      request.fail((err) => {
        RequestService.clearRequestTime()
        errorCallback(err)
      })
    }
    request.send()
  },

  // 新增模型配置
  addModel(params, callback) {
    const { modelType, provideCode, formData } = params;
    const postData = {
      id: formData.id,
      modelCode: formData.modelCode,
      modelName: formData.modelName,
      isDefault: formData.isDefault ? 1 : 0,
      isEnabled: formData.isEnabled ? 1 : 0,
      configJson: formData.configJson,
      docLink: formData.docLink,
      remark: formData.remark,
      sort: formData.sort || 0
    };

    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${modelType}/${provideCode}`)
      .method('POST')
      .data(postData)
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('新增模型失败:', err)
        this.$message.error(err.msg || '新增模型失败')
        RequestService.reAjaxFun(() => {
          this.addModel(params, callback)
        })
      }).send()
  },
  // 删除模型配置
  deleteModel(id, callback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${id}`)
      .method('DELETE')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('删除模型失败:', err)
        this.$message.error(err.msg || '删除模型失败')
        RequestService.reAjaxFun(() => {
          this.deleteModel(id, callback)
        })
      }).send()
  },
  // 获取模型名称列表
  getModelNames(modelType, modelName, callback, onTerminalFailure, retryCount = 0, retryStartedAt = 0) {
    const retryWindowStartedAt = retryStartedAt || Date.now();
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/names`)
      .method('GET')
      .data({ modelType, modelName })
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((error) => {
        retryCallbackRequest(
          (nextRetryCount, nextRetryStartedAt) => this.getModelNames(
            modelType,
            modelName,
            callback,
            onTerminalFailure,
            nextRetryCount,
            nextRetryStartedAt
          ),
          retryCount,
          onTerminalFailure,
          error,
          retryWindowStartedAt
        );
      });
    if (onTerminalFailure) {
      request.fail((error) => {
        RequestService.clearRequestTime();
        onTerminalFailure(error);
      });
    }
    request.send();
  },
  // 获取LLM模型名称列表
  getLlmModelCodeList(modelName, callback, onTerminalFailure, retryCount = 0, retryStartedAt = 0) {
    const retryWindowStartedAt = retryStartedAt || Date.now();
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/llm/names`)
      .method('GET')
      .data({ modelName })
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((error) => {
        retryCallbackRequest(
          (nextRetryCount, nextRetryStartedAt) => this.getLlmModelCodeList(
            modelName,
            callback,
            onTerminalFailure,
            nextRetryCount,
            nextRetryStartedAt
          ),
          retryCount,
          onTerminalFailure,
          error,
          retryWindowStartedAt
        );
      });
    if (onTerminalFailure) {
      request.fail((error) => {
        RequestService.clearRequestTime();
        onTerminalFailure(error);
      });
    }
    request.send();
  },
  // 获取模型音色列表
  getModelVoices(modelId, voiceName, callback, onTerminalFailure, retryCount = 0, retryStartedAt = 0) {
    const retryWindowStartedAt = retryStartedAt || Date.now();
    const queryParams = new URLSearchParams({
      voiceName: voiceName || ''
    }).toString();
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${modelId}/voices?${queryParams}`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((error) => {
        retryCallbackRequest(
          (nextRetryCount, nextRetryStartedAt) => this.getModelVoices(
            modelId,
            voiceName,
            callback,
            onTerminalFailure,
            nextRetryCount,
            nextRetryStartedAt
          ),
          retryCount,
          onTerminalFailure,
          error,
          retryWindowStartedAt
        );
      });
    if (onTerminalFailure) {
      request.fail((error) => {
        RequestService.clearRequestTime();
        onTerminalFailure(error);
      });
    }
    request.send();
  },
  // 音色试听（返回音频二进制 blob；modelId 为 TTS 模型ID）
  ttsVoicePreview(modelId, voice, text) {
    const queryParams = new URLSearchParams({
      modelId: modelId || '',
      voice: voice || ''
    });
    if (text) {
      queryParams.append('text', text);
    }
    const headers = {};
    try {
      const token = store.getters.getToken;
      if (token) {
        headers.Authorization = 'Bearer ' + JSON.parse(token).token;
      }
    } catch (e) {
      // token 解析失败时降级为无鉴权请求（后端将返回 401，由调用方提示）
    }
    return fetch(`${getServiceUrl()}/models/ttsPreview?${queryParams.toString()}`, {
      method: 'GET',
      headers
    }).then((response) => {
      if (!response.ok) {
        return response.json()
          .then((err) => {
            throw new Error(err.msg || `试听失败(${response.status})`);
          })
          .catch((e) => {
            if (e instanceof Error && e.message && e.message.indexOf('试听') !== -1) {
              throw e;
            }
            throw new Error(`试听失败(${response.status})`);
          });
      }
      return response.blob();
    });
  },
  // 获取单个模型配置
  getModelConfig(id, callback, errorCallback) {
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${id}`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('获取模型配置失败:', err)
        RequestService.reAjaxFun(() => {
          this.getModelConfig(id, callback, errorCallback)
        })
      })
    if (errorCallback) {
      request.fail((err) => {
        RequestService.clearRequestTime()
        errorCallback(err)
      })
    }
    request.send()
  },
  // 启用/禁用模型状态
  updateModelStatus(id, status, callback, errorCallback) {
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/enable/${id}/${status}`)
      .method('PUT')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('更新模型状态失败:', err)
        RequestService.reAjaxFun(() => {
          this.updateModelStatus(id, status, callback, errorCallback)
        })
      })
    if (errorCallback) {
      request.fail((err) => {
        RequestService.clearRequestTime()
        errorCallback(err)
      })
    }
    request.send()
  },
  // 更新模型配置
  updateModel(params, callback, errorCallback) {
    const { modelType, provideCode, id, formData } = params;
    const payload = {
      ...formData,
      configJson: formData.configJson
    };
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/${modelType}/${provideCode}/${id}`)
      .method('PUT')
      .data(payload)
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((err) => {
        console.error('更新模型失败:', err);
        RequestService.reAjaxFun(() => {
          this.updateModel(params, callback, errorCallback);
        });
      });
    if (errorCallback) {
      request.fail((err) => {
        RequestService.clearRequestTime();
        errorCallback(err);
      });
    }
    request.send();
  },
  // 设置默认模型
  setDefaultModel(id, callback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/default/${id}`)
      .method('PUT')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('设置默认模型失败:', err)
        this.$message.error(err.msg || '设置默认模型失败')
        RequestService.reAjaxFun(() => {
          this.setDefaultModel(id, callback)
        })
      }).send()
  },

  /**
   * 获取模型配置列表（支持查询参数）
   * @param {Object} params - 查询参数对象，例如 { name: 'test', modelType: 1 }
   * @param {Function} callback - 回调函数
   */
  getModelProvidersPage(params, callback) {
    // 构建查询参数
    const queryParams = new URLSearchParams();
    if (params.name) queryParams.append('name', params.name);
    if (params.modelType !== undefined) queryParams.append('modelType', params.modelType);
    if (params.page !== undefined) queryParams.append('page', params.page);
    if (params.limit !== undefined) queryParams.append('limit', params.limit);

    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/provider?${queryParams.toString()}`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((err) => {
        this.$message.error(err.msg || '获取供应器列表失败');
        RequestService.reAjaxFun(() => {
          this.getModelProviders(params, callback);
        });
      }).send();
  },

  /**
   * 新增模型供应器配置
   * @param {Object} params - 请求参数对象，例如 { modelType: '1', providerCode: '1', name: '1', fields: '1', sort: 1 }
   * @param {Function} callback - 成功回调函数
   */
  addModelProvider(params, callback) {
    const postData = {
      modelType: params.modelType || '',
      providerCode: params.providerCode || '',
      name: params.name || '',
      fields: JSON.stringify(params.fields || []),
      sort: params.sort || 0
    };

    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/provider`)
      .method('POST')
      .data(postData)
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((err) => {
        console.error('新增模型供应器失败:', err)
        this.$message.error(err.msg || '新增模型供应器失败')
        RequestService.reAjaxFun(() => {
          this.addModelProvider(params, callback);
        });
      }).send();
  },

  /**
   * 更新模型供应器配置
   * @param {Object} params - 请求参数对象，例如 { id: '111', modelType: '1', providerCode: '1', name: '1', fields: '1', sort: 1 }
   * @param {Function} callback - 成功回调函数
   */
  updateModelProvider(params, callback) {
    const putData = {
      id: params.id || '',
      modelType: params.modelType || '',
      providerCode: params.providerCode || '',
      name: params.name || '',
      fields: JSON.stringify(params.fields || []),
      sort: params.sort || 0
    };

    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/provider`)
      .method('PUT')
      .data(putData)
      .success((res) => {
        RequestService.clearRequestTime();
        callback(res);
      })
      .networkFail((err) => {
        this.$message.error(err.msg || '更新模型供应器失败')
        RequestService.reAjaxFun(() => {
          this.updateModelProvider(params, callback);
        });
      }).send();
  },
  // 删除
  deleteModelProviderByIds(ids, callback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/provider/delete`)
      .method('POST')
      .data(ids)
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res);
      })
      .networkFail((err) => {
        this.$message.error(err.msg || '删除模型供应器失败')
        RequestService.reAjaxFun(() => {
          this.deleteModelProviderByIds(ids, callback)
        })
      }).send()
  },
  // 获取插件列表
  getPluginFunctionList(params, callback, onTerminalFailure, retryCount = 0, retryStartedAt = 0) {
    const retryWindowStartedAt = retryStartedAt || Date.now();
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/provider/plugin/names`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        if (!onTerminalFailure && this.$message) {
          this.$message.error(err.msg || '获取插件列表失败');
        }
        retryCallbackRequest(
          (nextRetryCount, nextRetryStartedAt) => this.getPluginFunctionList(
            params,
            callback,
            onTerminalFailure,
            nextRetryCount,
            nextRetryStartedAt
          ),
          retryCount,
          onTerminalFailure,
          err,
          retryWindowStartedAt
        );
      });
    if (onTerminalFailure) {
      request.fail((error) => {
        RequestService.clearRequestTime();
        onTerminalFailure(error);
      });
    }
    request.send()
  },

  // 获取RAG模型列表
  getRAGModels(callback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/datasets/rag-models`)
      .method('GET')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('获取RAG模型列表失败:', err)
        this.$message.error(err.msg || '获取RAG模型列表失败')
        RequestService.reAjaxFun(() => {
          this.getRAGModels(callback)
        })
      }).send()
  },

  // 获取千问TTS平台模型ID列表（apiKey 需为千问/DashScope 平台密钥）
  getQwenTtsModels(apiKey, callback, errorCallback) {
    const request = RequestService.sendRequest()
      .url(`${getServiceUrl()}/models/qwenTtsModels`)
      .method('GET')
      .data({ apiKey })
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .networkFail((err) => {
        console.error('获取千问TTS模型列表失败:', err)
        if (errorCallback) {
          errorCallback(err)
        }
      })
    if (errorCallback) {
      request.fail((err) => {
        RequestService.clearRequestTime()
        errorCallback(err)
      })
    }
    request.send()
  }
}
