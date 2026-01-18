# NodeSeek 签到

自动签到 NodeSeek 论坛，支持 Cookie 持久化。

## 特点

- 使用 `curl_cffi` 模拟浏览器指纹绕过 Cloudflare
- Cookie 失效时自动使用 Playwright 登录
- 尝试通过 CDP 点击方式通过 Turnstile（无需打码平台）
- 支持多账号
- Cookie 自动保存供后续使用

## 环境变量

| 变量 | 说明 |
|------|------|
| NS_COOKIE | Cookie，多账号用 `&` 分隔 |
| NS_ACCOUNTS | 账号密码 `user:pass`，多账号用 `&` 分隔 |
| NS_RANDOM | 是否随机签到 `true/false` |
| TELEGRAM_BOT_TOKEN | Telegram 通知 |
| TELEGRAM_CHAT_ID | Telegram 聊天 ID |

## 青龙面板

订阅地址: `https://github.com/你的用户名/nodeseek-checkin.git`

## 本地运行

```bash
pip install curl_cffi playwright
playwright install chromium
python nodeseek-checkin.py
```
