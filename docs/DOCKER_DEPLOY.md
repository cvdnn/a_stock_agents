# A-Stock Agents Docker 部署指南

本项目全面支持 Docker 及 Docker Compose 容器化部署，具有**环境纯净**、**秒级交付**、**开箱即用**、**数据安全持久化**的特性。

---

## 🚀 快速启动 (Docker Compose 推荐)

### 1. 准备配置文件

进入项目根目录，复制环境变量模版：

```bash
cp .env.example .env
```

使用编辑器（如 `vim .env` 或 `nano .env`）配置您的大模型 API 密钥（如 DeepSeek、OpenAI、Gemini 等）：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
A_STOCK_DEFAULT_MODEL=deepseek-chat
```

### 2. 构建并启动容器

执行以下命令一键拉起容器：

```bash
docker compose up -d --build
```

*(如果在国内构建下载依赖较慢，可开启 `docker-compose.yml` 中的清华源 `PIP_INDEX_URL` 参数)*

### 3. 访问系统

启动成功后，即可通过浏览器访问：
- **Web 智能工作台**: [http://localhost:6300](http://localhost:6300)
- **API 交互式文档**: [http://localhost:6300/docs](http://localhost:6300/docs)
- **服务健康检查**: [http://localhost:6300/api/health](http://localhost:6300/api/health)

---

## 🛠️ 常用运维指令

### 查看运行状态与日志

```bash
# 查看容器状态（健康状况显示 healthy）
docker compose ps

# 查看实时日志
docker compose logs -f
```

### 停止与重启服务

```bash
# 停止容器
docker compose stop

# 启动容器
docker compose start

# 重启服务
docker compose restart

# 完全销毁容器（注意：宿主机 ./output 数据完整保留）
docker compose down
```

---

## 💻 容器内执行 CLI 量化命令

在无需进入容器的情况下，直接通过 Docker 调用项目内置的 17 项投研与量化 CLI 技能：

```bash
# 查询股票实时行情
docker compose exec astock-agents python scripts/core/cli.py data quote 600519 --json

# 7大分析师多空辩论
docker compose exec astock-agents python scripts/core/cli.py debate 600519 --json

# 查看股票池状态
docker compose exec astock-agents python scripts/core/cli.py pool list --json

# 5A 五维共振多因子选股
docker compose exec astock-agents python scripts/core/cli.py screen 5a --json
```

---

## 📦 纯 Docker CLI 单独运行方式 (可选)

如果不使用 Docker Compose，可以直接用原生 `docker` 命令进行构建与运行：

```bash
# 1. 构建镜像
docker build -t a-stock-agents:latest .

# 2. 运行容器
docker run -d \
  --name a_stock_agents \
  -p 6300:6300 \
  -v "$(pwd)/output:/app/output" \
  --env-file .env \
  a-stock-agents:latest

# 3. 容器内直接执行单次命令
docker run --rm \
  -v "$(pwd)/output:/app/output" \
  --env-file .env \
  a-stock-agents:latest astock data quote 000001 --json
```

---

## 📁 数据持久化说明

宿主机目录与容器内路径映射关系如下：

| 宿主机路径 | 容器内路径 | 说明 |
| :--- | :--- | :--- |
| `./output` | `/app/output` | **核心数据目录**（包含自选/持仓池 `positions.csv`、SQLite 对话历史 `chats.db`、研报输出、缓存等） |
| `./config` | `/app/config` | 核心全局配置（只读挂载，方便用户修改 `config.yaml` 覆盖默认规则） |
