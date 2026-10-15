# A-Stock Agents 工程运行约束

> 最新目录与交付定义：[技能开发工程与Release交付规范](skill-suite-portability-specification.md)。本文件只维护开发运行约束，不另行维护目录树。

## 工程与交付

本仓库开发、实现和测试技能，再构建Release供AI工具安装。开发初始化只管理本工程的依赖，不注册宿主、不创建项目技能发现链接、不修改系统Python。发布版本是生成产物，不作为维护源码的镜像。

技能唯一来源为skill_bundle/skills；公共算法唯一来源为skill_bundle/runtime/core；Web前后端在apps/web-console，复用公共实现。技能专属脚本留在自己的scripts，共用代码不得复制到每个技能。有效用户配置位于可写数据根的local/settings/application.yaml，技能环境变量位于local/settings/.env，公共清单位于skill_bundle/assets/config/skills_manifest.json。WebUI开发容器和端口配置位于tools/containers/web-console/。

## 代码根与数据根

从core.workspace导入PACKAGE_ROOT、SKILLS_ROOT、RUNTIME_ROOT及WORKSPACE_ROOT。PROJECT_ROOT保留为可写数据根兼容别名，不用它定位源码。禁止硬编码主机路径、依赖当前工作目录或固定父目录层数。

开发数据根默认仓库；Release数据根默认操作系统用户数据目录下a_stock_agents，显式环境变量绑定优先。output存用户交付结果与缓存，log存观测和审计，temp存可重建中间态，local存私有设置和运行环境变量。升级保留这些目录；发布全部排除。

## 执行与验证

Windows通过bin/astock.ps1或bin/astock.cmd，macOS/Linux通过bin/astock，通用Python入口为skill_bundle/runtime/cli.py；宿主Release使用包内runtime启动器。量化调用追加--json，日志与结构化输出分流。

基础能力不依赖Web登录或6300端口。Web用于开发调试，默认不进入技能Release。依赖模型、网络或后台任务的能力需明确声明。

自动门禁仅执行pytest -m core；扩展测试按[测试指南](testing-guide.md)取得人工确认。产物闭包、客户端安装、技能发现和能力调用分别验收，Windows验证不能替代macOS/Linux验证。
