# 腾讯API在AI-Platform terminal中"bad request"问题

## 问题说明

2026-07-21 实测：通过 `write_file` 将调用 `qt.gtimg.cn` 的 Python 脚本写到 `/tmp/` 然后用 `terminal("python3 /tmp/xxx.py")` 执行时，返回 "bad request"。

相同的数据通过技能脚本 `fetch_realtime.py --multi-quote/--tick` 调用（同样走腾讯/新浪链路）正常返回。

## 原因

疑似 WSL 下 Python urllib 的 HTTP 请求在通过 `write_file + terminal` 执行时被安全扫描阻断（与直接运行技能脚本的进程上下文不同）。

## 对策

当方案D（腾讯API直连裸调 `qt.gtimg.cn`）在 terminal 中返回 "bad request" 时：
1. 不要反复重试 — 问题不是临时性的
2. 直接降级到方案A（技能脚本 `fetch_realtime.py --multi-quote/--tick/--quote`）
3. 如果技能脚本也失败，再考虑其他备选

## 测试命令

```bash
# 验证用：
python3 -c "
import urllib.request
url = 'https://qt.gtimg.cn/q=sh600760'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
text = resp.read().decode('gbk')
print('OK' if '~' in text else 'FAIL')
"
```