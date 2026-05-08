# ngrok vs Cloudflare Tunnel 对比

> 目的：选择最适合 Medical-Health-Agent 项目的公网暴露方案。

---

## 核心对比

| 维度 | ngrok 免费版 | Cloudflare Tunnel |
|------|-------------|-------------------|
| **费用** | 免费 | 免费（需 Cloudflare 账号） |
| **域名** | 随机子域名，每次重启变化 | 固定域名（需自有域名或使用 Cloudflare 管理的域名） |
| **域名示例** | `abc123.ngrok-free.app` | `health.yourdomain.com` |
| **HTTPS** | 自动，ngrok 端 TLS 终止 | 自动，Cloudflare 边缘节点 TLS 终止 |
| **安装方式** | 下载 ngrok 二进制 | `cloudflared` 命令行工具 |
| **配置复杂度** | 极低，一条命令 | 中等，需配置 DNS 记录 + config.yml |
| **流量限制** | 1GB/月（免费版） | 无限制 |
| **连接数限制** | 40 连接/分钟 | 无 |
| **会话稳定性** | 可能有闲置断开（数小时） | 稳定长连接 |
| **启动速度** | 3 秒 | 5-10 秒 |
| **国内访问速度** | 取决于 ngrok 服务器（海外） | 取决于 Cloudflare 节点（有中国网络节点） |
| **登录态要求** | 需注册 + auth token | 需 Cloudflare 账号 + DNS 权限 |
| **适用场景** | 快速原型、开发测试、演示 | 长期运行、生产环境、需要固定 URL |

---

## 方案 A：ngrok 免费版（Phase 1 推荐）

### 优点

- **零配置**：下载 → 登录 → 一条命令启动
- **即开即用**：无需 DNS 配置、无需服务器
- **HTTPS 自动**：无需证书管理
- **本地热重载友好**：重启只需重新运行命令

### 缺点

- **URL 随机**：每次重启域名变化，需手动更新 iPhone 上的 URL（约 30 秒操作）
- **带宽限制**：1GB/月（个人健康数据通常 <200MB/月，足够）
- **会话限制**：闲置数小时可能断开（需重新启动）
- **无固定域名**：免费版不支持 reserved domain

### 安装 & 启动

```bash
# 1. 下载 ngrok (https://ngrok.com/download)
# 2. 注册免费账号获取 authtoken
ngrok config add-authtoken <your-token>

# 3. 启动
ngrok http 8000
```

### URL 随机问题应对

项目提供的 `start_pipeline.sh` 脚本会自动获取 ngrok 当前 URL 并打印，用户每次复制到 iPhone 即可。操作约 30 秒。

---

## 方案 B：Cloudflare Tunnel（长期推荐）

### 优点

- **固定域名**：一次配置永久使用
- **完全免费**：无带宽/连接数限制
- **高稳定性**：适合 7×24 运行
- **Cloudflare 生态**：可叠加 DDoS 防护、DNS 管理、Analytics 等
- **自定域名**：如 `health.yourdomain.com`

### 缺点

- **需要域名**：需拥有一个域名（.com/.xyz 等，约 $10/年），并托管 DNS 到 Cloudflare
- **配置步骤多**：需在 Cloudflare 控制台配置 DNS 和 Tunnel
- **首次设置约 15-30 分钟**：

### 安装 & 配置步骤

**前置条件**：拥有一个域名，并在 Cloudflare 中添加该站点（免费套餐即可）。

```bash
# 1. 安装 cloudflared
# macOS:
brew install cloudflared

# Windows (scoop):
scoop install cloudflared

# Linux (Debian/Ubuntu):
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# 2. 登录 Cloudflare
cloudflared tunnel login
# → 浏览器弹出 Cloudflare 授权页面，选择你的域名

# 3. 创建隧道
cloudflared tunnel create health-pipeline
# → 输出: Created tunnel <tunnel-id>

# 4. 创建配置文件 ~/.cloudflared/config.yml
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: health.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# 5. 配置 DNS
cloudflared tunnel route dns <tunnel-id> health.yourdomain.com
# → 自动在 Cloudflare DNS 中创建 CNAME 记录

# 6. 启动隧道
cloudflared tunnel run health-pipeline

# 7. （可选）安装为系统服务，开机自启
cloudflared service install
```

### 启动后

```
Health Auto Export URL:
  https://health.yourdomain.com/api/v1/health/sync
```

> **域名一旦配置后就永久不变**，无需每次启动修改 iPhone 配置。

---

## 推荐策略

```
Phase 1 (第 1-2 周)
  └── ngrok 免费版：快速打通数据流，验证可行性
       └── 接受 URL 随机，每次复制粘贴

验证成功 ↓

Phase 1 后期 / Phase 2
  └── Cloudflare Tunnel：切换到固定域名
       └── 配置一次，长期稳定运行
```

**选择依据**：
- 想**最快看到数据流动** → ngrok（5 分钟搞定）
- 想**一次配置永远省心** → Cloudflare Tunnel（30 分钟配置 + 需有域名）
- 想**两者兼备** → 先用 ngrok 验证，再迁移到 Cloudflare Tunnel
