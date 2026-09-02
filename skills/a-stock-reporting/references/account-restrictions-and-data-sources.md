# Account Trading Restrictions and Data Source Configuration

> Extracted from session-compress-20260622 (archived).
> These are stable configuration facts, not session-specific advice.

## Trading Account Restrictions

| Board | Code Prefix | Status |
|-------|:----------:|:------:|
| Shanghai Main Board | 60xxxx | Tradable |
| Shenzhen Main Board | 00xxxx | Tradable |
| ChiNext (创业板) | 30xxxx | ✗ Blocked |
| STAR Market (科创板) | 688/689xxx | ✗ Blocked |
| Beijing Stock Exchange | 8xxxxx | ✗ Blocked |

Scripts should filter blocked codes via `_is_blocked()` or equivalent.

## Data Source Configuration

- **akshare proxy-patch token**: Provided and configured
- **Virtual environment**: Uses a dedicated virtualenv for stock tools
- **System Python 3.9** has numpy version conflicts — not usable
- **a-share-data skill scripts**: Located under the skill's `scripts/` directory
- **API calls**: Should use fetch wrapping (e.g., proxy-patch init) for consistent behavior