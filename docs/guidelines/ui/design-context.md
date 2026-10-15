# A-Stock Agents Design Context

## Scope
- Project: `A-Stock Agents`
- Surface: Web research UI, desktop shell, reporting pages, and data-sync console
- Context source: inferred from current codebase and project UI guidelines

## Product Context
- Primary language: Simplified Chinese (`zh-CN`)
- Secondary language support: not explicitly defined in code; current UI is Chinese-first
- Target audience: professional A-share investors, quantitative traders, and institutional research users
- Brand personality: professional, rational, trustworthy, data-first, technology-oriented
- Core visual direction: clean light financial aesthetic
- Accessibility baseline: WCAG AA

## Design Constraints
- Follow A-share market convention: red means up, green means down
- Prefer system CJK-ready font stack:
  `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- Prefer subtle borders and light cards over strong decorative stripes
- Use tabular numerals for prices, percentages, volumes, and financial metrics
- Keep motion restrained: mostly `150ms` to `300ms`

## Current Token Sources
- Primary runtime tokens: [`apps/web-console/frontend/css/style.css`](../../../apps/web-console/frontend/css/style.css)
- UI guideline: [`ui-design-guide.md`](ui-design-guide.md)
- Data-sync visual contract: [`market-data-sync-control-console-specification.md`](market-data-sync-control-console-specification.md)

## Known Token Notes
- Main brand blue is stable at `#1677FF`
- A-share semantic colors are stable at `#F5222D` and `#52C41A`
- Background token has a small drift between docs and code:
  - guideline often uses `#F8FAFD`
  - root token currently uses `#F6F8FC`
- Report/export HTML uses a separate document-oriented palette and should not replace the main workbench palette

## Working Assumptions
- This is development guidance for the optional WebUI; it is not part of the skill Release.
- If the product later adds multilingual or dark theme support, update this context before expanding the token system.
