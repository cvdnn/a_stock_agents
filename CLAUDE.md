# A-Stock Agents — Claude Code Instructions

This project is a self-contained, production-ready quantitative research and multi-agent system for China A-Share markets.

## Primary Guidelines
1. **Zero Global Pollution**: All 17 skills are loaded in-place within this workspace. Never copy or install skills to global system directories.
2. **Execution Contract**: When performing quant calculations, quotes, 5A screening, or risk control, **always use the unified CLI**:
   - macOS / Linux: `./bin/astock <subcommand> --json`
   - Windows: `.\bin\astock.cmd <subcommand> --json`
   - Cross-platform: `python scripts/core/cli.py <subcommand> --json`
3. **Skills & Rules**:
   - Comprehensive skill manifest and intent routing rules are defined in [`AGENTS.md`](./AGENTS.md) and [`config/skills_manifest.json`](./config/skills_manifest.json).
   - In-place skill definitions are located in [`.agents/skills/<skill_id>/SKILL.md`](./.agents/skills). Read them as needed.
