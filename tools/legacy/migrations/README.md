# 历史迁移脚本归档 (Historical Migration Scripts)

本目录归档 2026-10-14 至 2026-10-15 期间，项目从旧工程结构迁移至 `skill_bundle/` 单一来源与锚点技能架构时使用的一次性脚本：

- `migrate_skill_suite.py`：技能目录初次迁移与布局脚本
- `repair_skill_suite_paths.py`：旧路径修复与相对链接规整脚本
- `finalize_skill_suite.py`：迁移后收尾校验与生成辅助
- `close_skill_suite_migration.py`：迁移关闭与一致性锁定
- `refine_release_scope.py`：早期 Release 打包白名单微调
- `reorganize_root_tools.py`：根目录工具分类规整

> [!NOTE]
> 以上脚本已全部完成历史使命，保留仅作审计与历史追溯参考。日常开发、构建与验证请使用 `tools/packaging/` 与 `tools/validation/` 活跃工具。
