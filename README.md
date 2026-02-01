# NodeSeek & DeepFlood 签到

自动签到 NodeSeek 和 DeepFlood 论坛，支持 Cookie 持久化。

## 特点

- 同时支持 NodeSeek 和 DeepFlood 签到
- 使用 `curl_cffi` 模拟浏览器指纹 (Safari) 绕过 Cloudflare
- DeepFlood 自动通过 NodeSeek OAuth 获取 Cookie
- Cookie 自动保存到本地缓存和青龙环境变量
- Cookie 失效时使用 YesCaptcha 解决 Turnstile 并重新登录
- 支持多账号

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| NODESEEK_COOKIE | 否 | NodeSeek Cookie，多账号用 `&` 分隔 |
| NODESEEK_ACCOUNT | 否 | 账号密码 `user:pass`，多账号用 `&` 分隔 |
| DEEPFLOOD_COOKIE | 否 | DeepFlood Cookie（不设置则自动通过 OAuth 获取） |
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

### DeepFlood 签到

DeepFlood 和 NodeSeek 是两个独立的站点，但支持通过 NodeSeek 账号 OAuth 登录。

- 如果设置了 `DEEPFLOOD_COOKIE`，直接使用
- 如果未设置，会自动通过 NodeSeek OAuth 获取 DeepFlood Cookie
- 获取的 Cookie 会自动保存到本地缓存，下次运行时优先使用

## 本地缓存

Cookie 会自动保存到 `cookies_cache.json` 文件，包括：
- NodeSeek Cookie（登录后自动保存）
- DeepFlood Cookie（OAuth 获取后自动保存）

## 青龙面板

订阅: `https://github.com/donma033x/nodeseek-checkin.git`

环境变量配置：
- `NODESEEK_ACCOUNT`: 账号密码
- `YESCAPTCHA_API_KEY`: YesCaptcha 密钥
- `DEEPFLOOD_COOKIE`: DeepFlood Cookie（可选）

## 运行示例

```
[09:15:00] [签到] ℹ NodeSeek & DeepFlood 签到开始
[09:15:00] [签到] ℹ 共 1 个账号
[09:15:00] [NodeSeek] ⏳ [默认账号] 签到中...
[09:15:01] [NodeSeek] ✓ [默认账号] ✓ 今天的签到收益是6个鸡腿
[09:15:01] [DeepFlood] ⏳ [默认账号] 签到中...
[09:15:01] [DeepFlood] ⏳ Cookie 无效，通过 OAuth 重新获取...
[09:15:02] [DeepFlood] ⏳ 通过 NodeSeek OAuth 获取 Cookie...
[09:15:03] [DeepFlood] ✓ OAuth 登录成功
[09:15:03] [DeepFlood] ✓ Cookie 已保存到本地缓存
[09:15:03] [DeepFlood] ✓ [默认账号] ✓ 今天的签到收益是4个鸡腿
[09:15:03] [签到] ✓ 完成 - 2/2 成功
```
