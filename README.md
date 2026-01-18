# NodeSeek 签到

自动签到 NodeSeek 论坛，支持 Cookie 持久化。

## 特点

- 使用 `curl_cffi` 模拟浏览器指纹 (Safari) 绕过 Cloudflare
- Cookie 自动保存到青龙环境变量
- Cookie 失效时使用 YesCaptcha 解决 Turnstile 并重新登录
- 支持多账号

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| NODESEEK_COOKIE | 否 | Cookie，多账号用 `&` 分隔 |
| NODESEEK_ACCOUNT | 否 | 账号密码 `user:pass`，多账号用 `&` 分隔 |
| NODESEEK_RANDOM | 否 | 是否随机签到 `true/false`，默认 true |
| YESCAPTCHA_API_KEY | 登录时需要 | YesCaptcha API Key（解决 Turnstile） |
| TELEGRAM_BOT_TOKEN | 否 | Telegram 通知 |
| TELEGRAM_CHAT_ID | 否 | Telegram 聊天 ID |

## 使用说明

### 有 Cookie 时

直接使用 Cookie 签到，无需 YesCaptcha：

```bash
export NODESEEK_COOKIE="your_cookie_here"
python nodeseek-checkin.py
```

### 无 Cookie 或 Cookie 失效时

需要配置 YesCaptcha 来解决登录时的 Turnstile 验证：

```bash
export NODESEEK_ACCOUNT="username:password"
export YESCAPTCHA_API_KEY="your_key"
python nodeseek-checkin.py
```

## 青龙面板

订阅: `https://github.com/donma033x/nodeseek-checkin.git`

环境变量配置：
- `NODESEEK_ACCOUNT`: 账号密码
- `YESCAPTCHA_API_KEY`: YesCaptcha 密钥
