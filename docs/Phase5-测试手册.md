# Phase 5 前端测试手册（内测版）

> 目标：本地启动 H5 前端 → 连接后端 → 验收 4 个页面功能

---

## 一、环境准备

### 1.1 依赖安装

```powershell
cd C:\Users\Lenovo\Desktop\Medical-Health-Agent\frontend
npm install
```

### 1.2 启动后端

```powershell
# 另开终端
cd C:\Users\Lenovo\Desktop\Medical-Health-Agent
python -m data_pipeline.webhook_server
```

### 1.3 启动前端

```powershell
cd C:\Users\Lenovo\Desktop\Medical-Health-Agent\frontend
npm run dev
```

浏览器打开 `http://localhost:5173`。

### 1.4 本地代理说明

Vite 已配置代理：前端所有 `/api/*` 请求自动转发到 `http://localhost:8000`。**本地测试无需 ngrok**，也无需在设置页改地址——保持默认空值即可直接连通。

---

## 二、页面验收

### 2.1 对话页 (Chat)

| #   | 操作                | 预期                              |
| --- | ----------------- | ------------------------------- |
| 1   | 打开 Chat Tab       | 显示"我是您的私人健康顾问"欢迎语               |
| 2   | 输入"你好"，点发送        | AI 回复问候语                        |
| 3   | 输入"小孩发烧39度怎么办"，发送 | AI 回复含医学知识，intent=medical_qa    |
| 4   | 输入"我今天心率怎么样"，发送   | AI 回复含今日心率数据，intent=health_data |
| 5   | 输入"胸痛呼吸困难"，发送     | 红色紧急提示 + safety_level=emergency |
| 6   | 点"✚ 新对话"          | 清空消息列表                          |
| 7   | 点"☰ 会话"           | 弹出会话列表                          |
| 8   | 点某条历史会话           | 加载该会话的聊天记录                      |

### 2.2 健康看板 (Dashboard)

| #   | 操作               | 预期                    |
| --- | ---------------- | --------------------- |
| 1   | 打开 Dashboard Tab | 顶部显示同步状态 + 时间         |
| 2   | 查看指标卡片           | 心率/步数/能量/呼吸等 2×4 网格排列 |
| 3   | 查看指示状态           | 偏离基线标注 ↑偏高 / ↓偏低 / 正常 |
| 4   | 查看趋势图            | 心率 + 步数 4 周柱状图 + 趋势方向 |
| 5   | 后端停止后刷新          | 显示"网络不可达"提示           |
| 6   | 无数据时             | 卡片显示 --，图表显示"数据收集中"   |

### 2.3 周报页 (Report)

| # | 操作 | 预期 |
|---|------|------|
| 1 | 打开 Report Tab | 显示历史周报列表（横滑） |
| 2 | 点本周周报 | 加载 LLM 叙事 + 指标表格 |
| 3 | 点"生成本周周报" | 按钮变"生成中..."且禁用，完成后展示 |
| 4 | 无周报时 | 显示"暂无周报" + 生成按钮 |
| 5 | 左右滑动周列表 | 切换不同周 |

### 2.4 设置页 (Settings)

| #   | 操作              | 预期                         |
| --- | --------------- | -------------------------- |
| 1   | 打开 Settings Tab | 显示 API 地址输入框 + 数据同步信息 + 关于 |
| 2   | 点"检测"           | 🟢 服务正常 / 🔴 无法连接          |
| 3   | 地址栏清空（恢复默认）→检测  | 🟢 服务正常（走 Vite 代理）         |
| 4   | 点"保存地址"         | Toast "已保存"                |
| 5   | 查看数据同步          | 最近同步时间 + 入库总数              |

---

## 三、多轮对话验收

```powershell
# 快速验证
python -c "
import requests
s = requests.Session()
r = s.post('http://localhost:8000/api/v1/chat', json={'query':'今天心率怎么样？'})
sid = r.json()['session_id']
print('Session:', sid, '|', r.json()['response'][:80])
r2 = s.post('http://localhost:8000/api/v1/chat', json={'query':'跟昨天比呢？', 'session_id': sid})
print('Follow-up:', r2.json()['response'][:80])
"
```

**预期**：追问返回与前文心率相关的回答。

---

## 四、完整验收清单

| # | 页面 | 测试项 | 通过 |
|---|------|--------|------|
| 1 | Chat | 单轮医学问答 | ☐ |
| 2 | Chat | health_data 查询 | ☐ |
| 3 | Chat | 紧急词短路 | ☐ |
| 4 | Chat | 多轮追问 | ☐ |
| 5 | Chat | 历史会话列表 | ☐ |
| 6 | Chat | 新对话清空 | ☐ |
| 7 | Dashboard | 指标卡片展示 | ☐ |
| 8 | Dashboard | 基线对比状态 | ☐ |
| 9 | Dashboard | 4周趋势图 | ☐ |
| 10 | Dashboard | 空数据降级 | ☐ |
| 11 | Report | 周报列表 | ☐ |
| 12 | Report | 周报叙事展示 | ☐ |
| 13 | Report | 生成按钮 + loading | ☐ |
| 14 | Settings | API 检测 | ☐ |
| 15 | Settings | 地址保存持久化 | ☐ |
| 16 | Settings | 同步状态展示 | ☐ |
| 17 | 全局 | 弱网错误提示 | ☐ |
| 18 | 全局 | Tab 切换正常 | ☐ |

---

## 五、项目文件总览

```
frontend/
├── index.html                     ← 入口 (含 viewport mobile 适配)
├── package.json                   ← Vue 3 + Vite + Pinia + Vue Router
├── vite.config.js                 ← /api → localhost:8000 代理
└── src/
    ├── main.js                    ← Vue Router 4 路由定义
    ├── App.vue                    ← 底部 TabBar + 全局 Toast + 480px 居中
    ├── api/
    │   ├── request.js             ← fetch 封装 (30s超时 + 错误Toast)
    │   ├── chat.js                ← /chat + /memory API
    │   ├── health.js              ← /health API
    │   └── report.js              ← /report API
    ├── stores/
    │   ├── chat.js                ← Pinia 对话状态
    │   ├── health.js              ← Pinia 健康数据状态
    │   ├── report.js              ← Pinia 周报状态
    │   └── app.js                 ← 全局配置 (BASE_URL + 服务检测)
    └── pages/
        ├── chat/index.vue         ← 对话页 (气泡 + 会话侧栏)
        ├── dashboard/index.vue    ← 健康看板 (卡片 + 柱状图 + 基线)
        ├── report/index.vue       ← 周报页 (横滑选择 + LLM叙事)
        └── settings/index.vue     ← 设置页 (URL编辑 + 同步状态 + 关于)
```

---

## 六、已修复的常见问题

| 问题 | 原因 | 修复 |
|------|------|------|
| `npm run dev:h5` 报错 | uni-app → Vue 3 重构后命令变了 | 用 `npm run dev` |
| 设置页"检测"无反应 | store 使用了动态 `await import()` 失败 | 改为顶部直接 `import` |
| 页面不响应手机尺寸 | 缺少 `max-width: 480px` 容器 | `#app-root { max-width: 480px; margin: 0 auto }` |
| 按钮上是文字光标 | 未设 `cursor: pointer` | 全局 `button { cursor: pointer }` |
| 对话 422 错误 | Pydantic `session_id: str = None` 拒绝 `null` | 改为 `Optional[str] = None` |
| 不需要 ngrok | Vite 已配代理 `/api → localhost:8000` | 本地测试直接 `npm run dev` |

