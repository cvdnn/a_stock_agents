# 可选 Web 调试容器指南

Docker属于开发辅助工具，不是技能Release安装前提。当前文件仅用于调试apps/web-console；基础技能通过runtime/CLI执行，不要求HTTP服务或Docker。

## 文件位置与职责

- tools/containers/web-console/Dockerfile：Web调试镜像定义，只复制技能集合、Web应用和入口。
- tools/containers/web-console/compose.yaml：显式启动的开发组合，无自动重启和固定容器名。
- tools/containers/web-console/entrypoint.sh：默认启动Web，可显式执行一次性CLI。
- tools/containers/web-console/Dockerfile.dockerignore：按 WebUI Dockerfile 单独排除开发文件；local/output/log/temp和私有环境文件不进入镜像。

## 配置和数据

技能运行配置和凭据保存在`local/settings/`，可从`skill_bundle/assets/config/runtime.env.example`创建`.env`。WebUI端口等开发参数独立放在`tools/containers/web-console/.env`；首次使用时从该目录的`.env.example`复制，后续Compose命令用`--env-file`读取端口配置。示例本机监听127.0.0.1；Compose在容器内监听0.0.0.0，发布端口只绑定宿主回环。A_STOCK_RUNTIME_MODE=production保留认证策略，不表示调试容器已经通过生产验收。

容器代码在/app，数据根在/data。Compose显式覆盖数据路径，避免把宿主`local/settings/.env`中的绝对路径直接当容器路径。

| 宿主目录 | 容器目录 | 用途 |
|---|---|---|
| output | /data/output | 用户结果、报告、缓存 |
| local | /data/local | 有效配置、数据库及本地市场状态 |
| log | /data/log | 日志及审计 |
| 无持久化绑定 | /data/temp | UID1000可写的tmpfs，容器移除即清理 |

有效配置为/data/local/settings/application.yaml；local必须可写，不能将整个目录只读挂载。该环境会访问绑定的开发数据；隔离测试应使用测试fixture另建临时数据根，不能复用真实local/output。

Linux宿主需事先确认绑定目录对UID1000可写；不自动递归修改宿主权限。Windows/macOS依赖Docker Desktop的共享目录与权限，实际运行需分别验证。

## 后续显式使用命令

以下仅是使用说明，不代表本轮已执行构建或启动：

```bash
# 在仓库根执行；首次使用需要明确构建镜像
# 不属于本轮“无需构建”任务
# docker compose --env-file tools/containers/web-console/.env -f tools/containers/web-console/compose.yaml build

# 使用已存在的镜像，按需启动；不自动构建
# docker compose --env-file tools/containers/web-console/.env -f tools/containers/web-console/compose.yaml up --no-build

# 查看状态与停止
# docker compose --env-file tools/containers/web-console/.env -f tools/containers/web-console/compose.yaml ps
# docker compose --env-file tools/containers/web-console/.env -f tools/containers/web-console/compose.yaml down
```

容器CLI示例：docker compose -f tools/containers/web-console/compose.yaml run --rm --no-deps web-console astock data quote 600519 --json。此命令会触网，须在明确授权的行情或验证任务中执行；一次性CLI不以HTTP HEALTHCHECK判断成功。

requirements.txt从现有uv.lock导出并固定基础版本，使用tools/development/export_dependencies.py（Python3.11+，离线，不修改锁）。基础声明不一致时导出拒绝执行。浏览器/并行测试extras未全部进入现有锁；开发初始化显式安装test，browser/full另选，并以基础requirements约束版本。锁补齐应作为显式依赖维护任务，不在不构建任务中重解析。

本轮未构建镜像、未启动容器，未证明容器可运行；Docker实测与三系统兼容须单独登记。
