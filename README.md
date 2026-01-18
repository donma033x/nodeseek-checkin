# NodeSeek 签到

自动签到 NodeSeek 论坛，支持 Cookie 持久化。

## 特点

- 使用 `curl_cffi` 模拟浏览器指纹 (Safari) 绕过 Cloudflare
- Cookie 自动保存供后续使用
- Cookie 失效时使用 YesCaptcha 解决 Turnstile 并重新登录
- 支持多账号

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| NS_COOKIE | 否 | Cookie，多账号用 `&` 分隔 |
| NS_ACCOUNTS | 否 | 账号密码 `user:pass`，多账号用 `&` 分隔 |
| NS_RANDOM | 否 | 是否随机签到 `true/false`，默认 true |
| YESCAPTCHA_KEY | 登录时需要 | YesCaptcha API Key（解决 Turnstile） |
| TELEGRAM_BOT_TOKEN | 否 | Telegram 通知 |
| TELEGRAM_CHAT_ID | 否 | Telegram 聊天 ID |

## 使用说明

### 1. 有 Cookie 时

直接使用 Cookie 签到，无需 YesCaptcha：

```bash
export NS_COOKIE="your_cookie_here"
python nodeseek-checkin.py
```

### 2. 无 Cookie 或 Cookie 失效时

需要配置 YesCaptcha 来解决登录时的 Turnstile 验证：

1. 注册 [YesCaptcha](https://yescaptcha.com/i/k2Hy3Q)
2. 联系客服可免费获得约 60 次额度

```bash
export NS_ACCOUNTS="username:password"
export YESCAPTCHA_KEY="your_key"
python nodeseek-checkin.py
```

### 青龙面板

订阅: `https://github.com/你的用户名/nodeseek-checkin.git`

在青龙环境变量中配置 `NS_ACCOUNTS` 和 `YESCAPTCHA_KEY`。

## 为什么需要 YesCaptcha？

NodeSeek 登录时使用 Cloudflare Turnstile 人机验证。在无头浏览器/虚拟显示器环境下，Turnstile 会检测到并拒绝通过。

**一旦成功登录，Cookie 会被保存，后续签到无需再次验证。**

## 本地运行

```bash
pip install curl_cffi requests
python nodeseek-checkin.py
```
