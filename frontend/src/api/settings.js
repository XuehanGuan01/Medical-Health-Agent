import request from './request'

/** 获取所有可用模型列表（按系列分组） */
export const getModels = () =>
  request('/api/v1/settings/models')

/** 获取当前使用的模型 */
export const getCurrentModel = () =>
  request('/api/v1/settings/model')

/** 切换模型 */
export const switchModel = (provider) =>
  request('/api/v1/settings/model', {
    method: 'POST',
    data: { provider },
  })

/** 测试模型连通性 */
export const testModel = (provider) =>
  request('/api/v1/settings/model/test', {
    method: 'POST',
    data: { provider },
  })

/** 获取模型切换历史 */
export const getModelHistory = () =>
  request('/api/v1/settings/model/history')
