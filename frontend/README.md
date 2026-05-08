# Medical-Health-Agent 小程序前端

基于 **uni-app (Vue 3)** 构建，首选目标平台：微信小程序。

## 技术栈

- 框架：uni-app (Vue 3)
- 状态管理：Pinia
- HTTP 请求：uni.request / axios
- UI 组件：uni-ui

## 目标平台

1. 微信小程序（首选）
2. 支付宝小程序
3. H5 (Web)
4. App (iOS/Android) — 可选

## 项目初始化（Phase 5 执行）

```bash
# 安装 HBuilderX 或 uni-app CLI
npm install -g @dcloudio/uvm

# 创建项目
npx degit dcloudio/uni-preset-vue#vite-ts frontend
cd frontend
npm install

# 启动开发
npm run dev:mp-weixin   # 微信小程序
npm run dev:h5           # H5
```
