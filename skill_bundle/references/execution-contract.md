# 共享执行契约

集合由bundle.json标识，skills/runtime/assets/references完整交付。统一执行：Python运行runtime/cli.py <command> --json；基础技能不依赖Web。

A_STOCK_WORKSPACE_ROOT绑定用户工作区；旧A_STOCK_AGENTS_ROOT兼容为工作区。开发默认仓库根；Release默认操作系统用户数据目录下a_stock_agents，安装缓存不作为可写数据目录。用户有效配置位于local/settings/application.yaml，可由A_STOCK_CONFIG_PATH显式指定，不回退其他实例。

代码与资源根由模块真实路径和集合标识定位，不依赖当前目录或链接别名。output是最终交付物，log是审计，temp是可重建暂存，local是私有状态。升级不替换用户状态。

AI工具使用Release；开发仓库不提供项目发现入口。Release不依赖链接，宿主注册需要的引用另行验收。20个入口包含总入口与19项专业技能，真实宿主发现数另行验证。
