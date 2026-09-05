# 账户交易限制配置

## 概述

`a-share-dashboard` 支持通过 `config.yaml` 配置账户可交易的板块。
所有脚本在添加或开仓时自动检查限制并拒绝受限股票。

## 配置方式

编辑 `config.yaml` 中的 `account` 节：

```yaml
account:
  allowed_boards:
    sh_main: true        # 上海主板 (60xxxx)
    sz_main: true        # 深圳主板 (00xxxx)
    sz_gem: false        # 创业板 (30xxxx) - 当前禁止
    sh_kcb: false        # 科创板 (688xxx)
    bj: false            # 北交所 (8xxxxx)

  blocked_prefixes:
    - "688"
    - "689"
    - "30"
    - "8"
    - "4"
    - "83"
```

## 当前配置（2026-06-22）

| 板块 | 代码前缀 | 状态 |
|------|:--------:|:----:|
| 上海主板 | 60xxxx | ✓ 可交易 |
| 深圳主板 | 00xxxx | ✓ 可交易 |
| 创业板 | 30xxxx | ✗ 禁止 |
| 科创板 | 688/689 | ✗ 禁止 |
| 北交所 | 8xxxxx | ✗ 禁止 |
| 老三板 | 4xxxxx | ✗ 禁止 |

## 代码集成

| 脚本 | 函数 | 拦截点 |
|------|------|--------|
| `pool_manager.py` | `_is_blocked(code)` | `cmd_add()` 拒绝添加 |
| `position_manager.py` | `_is_blocked(code)` | `cmd_open()` 拒绝开仓 |
| `tdx_sync.py` | `blocked` 计数 | `cmd_import()` 跳过 |

## 覆盖限制

编辑 `config.yaml` 将对应板块设为 `true`，重启脚本即可。无需修改代码。