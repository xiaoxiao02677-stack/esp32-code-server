import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

export default {
    // 分页查询设备云端配置
    getDeviceConfigList(params, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/deviceConfigMag`)
            .method('GET')
            .data(params)
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('获取设备云端配置列表失败:', err);
                RequestService.reAjaxFun(() => {
                    this.getDeviceConfigList(params, callback);
                });
            }).send();
    },
    // 查询单台设备云端配置
    getDeviceConfig(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/deviceConfigMag/${id}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('获取设备云端配置失败:', err);
                RequestService.reAjaxFun(() => {
                    this.getDeviceConfig(id, callback);
                });
            }).send();
    },
    // 删除单台设备云端配置
    deleteDeviceConfig(id, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/deviceConfigMag/${id}`)
            .method('DELETE')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('删除设备云端配置失败:', err);
                RequestService.reAjaxFun(() => {
                    this.deleteDeviceConfig(id, callback);
                });
            }).send();
    },
    // 清空全部设备云端配置
    clearAllDeviceConfigs(callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/deviceConfigMag`)
            .method('DELETE')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res);
            })
            .networkFail((err) => {
                console.error('清空设备云端配置失败:', err);
                RequestService.reAjaxFun(() => {
                    this.clearAllDeviceConfigs(callback);
                });
            }).send();
    }
}
