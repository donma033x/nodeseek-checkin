#!/usr/bin/env python3
"""
NodeSeek 论坛自动签到脚本

cron: 0 9 * * *
new Env('nodeseek-checkin')

环境变量:
    NS_COOKIE: Cookie（多账号用 & 分隔）
    NS_ACCOUNTS: 账号密码 email:password（多账号用 & 分隔，当 Cookie 失效时使用）
    NS_RANDOM: 是否随机签到 true/false（默认 true）
    TELEGRAM_BOT_TOKEN: Telegram 通知（可选）
    TELEGRAM_CHAT_ID: Telegram 聊天ID（可选）
"""

import os
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================
NS_COOKIE = os.environ.get('NS_COOKIE', '')
NS_ACCOUNTS = os.environ.get('NS_ACCOUNTS', '')
NS_RANDOM = os.environ.get('NS_RANDOM', 'true').lower() == 'true'
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

COOKIE_FILE = Path(__file__).parent / "cookies.json"
TURNSTILE_SITEKEY = "0x4AAAAAAAaNy7leGjewpVyR"

# ==================== 日志 ====================
class Logger:
    @staticmethod
    def log(tag, msg, icon="ℹ"):
        icons = {"OK": "✓", "WARN": "⚠", "WAIT": "⏳", "INFO": "ℹ", "ERR": "✗"}
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] [{tag}] {icons.get(icon, icon)} {msg}")

# ==================== Cookie 管理 ====================
def load_cookies():
    """从文件加载 cookies"""
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_cookies(cookies_dict):
    """保存 cookies 到文件"""
    with open(COOKIE_FILE, 'w') as f:
        json.dump(cookies_dict, f, indent=2)
    Logger.log("Cookie", f"已保存到 {COOKIE_FILE}", "OK")

# ==================== 签到（使用 curl_cffi）====================
def do_checkin(cookie, random=True):
    """执行签到"""
    try:
        from curl_cffi import requests
    except ImportError:
        Logger.log("签到", "安装 curl_cffi...", "WAIT")
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'origin': 'https://www.nodeseek.com',
        'referer': 'https://www.nodeseek.com/board',
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    
    url = f"https://www.nodeseek.com/api/attendance?random={'true' if random else 'false'}"
    
    # 尝试不同的浏览器指纹
    impersonates = ['safari15_5', 'safari15_3', 'chrome120', 'chrome119', 'chrome110']
    
    for imp in impersonates:
        try:
            resp = requests.post(url, headers=headers, json={}, impersonate=imp, timeout=30)
            if resp.status_code == 403:
                if "challenge" in resp.text.lower() or "cf-chl" in resp.text.lower():
                    Logger.log("签到", f"403 CF挑战 ({imp})，尝试下一个...", "WARN")
                    continue
            
            data = resp.json()
            msg = data.get("message", "")
            
            if "鸡腿" in msg or data.get("success"):
                return "success", msg
            elif "已完成签到" in msg:
                return "already", msg
            elif data.get("status") == 404:
                return "invalid", msg
            else:
                return "fail", msg
        except Exception as e:
            Logger.log("签到", f"请求异常 ({imp}): {e}", "WARN")
            continue
    
    return "error", "所有指纹都失败"

# ==================== Playwright 登录获取 Cookie ====================
async def cdp_click(cdp, x, y):
    """使用 CDP 模拟点击"""
    await cdp.send('Input.dispatchMouseEvent', {
        'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1
    })
    await asyncio.sleep(0.05)
    await cdp.send('Input.dispatchMouseEvent', {
        'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'clickCount': 1
    })

async def handle_turnstile(page, cdp, max_wait=30):
    """处理 Turnstile 验证"""
    Logger.log("Turnstile", "等待验证框...", "WAIT")
    
    # 等待 Turnstile 加载
    for _ in range(10):
        turnstile = await page.evaluate('''() => {
            const el = document.querySelector('.cf-turnstile, [data-sitekey]');
            if (el) { 
                const r = el.getBoundingClientRect(); 
                return {x: r.x, y: r.y, w: r.width, h: r.height}; 
            }
            return null;
        }''')
        if turnstile and turnstile.get('w', 0) > 0:
            break
        await asyncio.sleep(1)
    
    if not turnstile:
        Logger.log("Turnstile", "未找到验证框", "INFO")
        return True
    
    # CDP 点击
    x = int(turnstile['x'] + 30)
    y = int(turnstile['y'] + 32)
    Logger.log("Turnstile", f"CDP 点击 ({x}, {y})", "INFO")
    await cdp_click(cdp, x, y)
    
    # 等待验证完成
    for i in range(max_wait):
        await asyncio.sleep(1)
        token = await page.evaluate('() => document.querySelector("input[name=cf-turnstile-response]")?.value || ""')
        if len(token) > 10:
            Logger.log("Turnstile", f"验证通过 ({i+1}s)", "OK")
            return True
        if i % 5 == 0 and i > 0:
            Logger.log("Turnstile", f"等待中... {i}s", "WAIT")
    
    Logger.log("Turnstile", "验证超时", "WARN")
    return False

async def login_and_get_cookie(username, password):
    """使用 Playwright 登录获取 Cookie"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        Logger.log("登录", "安装 playwright...", "WAIT")
        os.system("pip install playwright -q && playwright install chromium")
        from playwright.async_api import async_playwright
    
    Logger.log("登录", f"账号: {username}", "WAIT")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        cdp = await context.new_cdp_session(page)
        
        try:
            # 访问登录页
            Logger.log("登录", "访问登录页...", "WAIT")
            await page.goto("https://www.nodeseek.com/signIn.html", timeout=60000)
            await asyncio.sleep(3)
            
            # 检查是否有 CF 挑战页
            content = await page.content()
            if "Just a moment" in content or "cf-chl" in content:
                Logger.log("登录", "检测到 CF 挑战页，等待...", "WAIT")
                await asyncio.sleep(10)
            
            # 填写表单
            Logger.log("登录", "填写登录表单...", "INFO")
            # Email/用户名输入框
            await page.fill('input[placeholder="Email"], input[type="email"], input[type="text"]', username)
            await page.fill('input[placeholder="Password"], input[type="password"]', password)
            await asyncio.sleep(1)
            
            # 处理 Turnstile
            if not await handle_turnstile(page, cdp):
                Logger.log("登录", "Turnstile 验证失败", "ERR")
                return None
            
            # 点击登录按钮
            Logger.log("登录", "点击登录...", "INFO")
            await page.click('button:has-text("登录"), button[type="submit"]')
            await asyncio.sleep(5)
            
            # 检查登录结果
            current_url = page.url
            if "signIn" not in current_url.lower():
                Logger.log("登录", "登录成功！", "OK")
                
                # 获取 cookies
                cookies = await context.cookies()
                cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
                return cookie_str
            else:
                Logger.log("登录", "登录失败", "ERR")
                return None
                
        except Exception as e:
            Logger.log("登录", f"异常: {e}", "ERR")
            return None
        finally:
            await browser.close()

# ==================== 通知 ====================
def send_telegram(msg):
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        Logger.log("通知", f"发送失败: {e}", "WARN")

# ==================== 主流程 ====================
async def process_account(identifier, cookie=None, username=None, password=None):
    """处理单个账号"""
    result = {"id": identifier, "status": "", "msg": ""}
    
    # 先尝试用 cookie 签到
    if cookie:
        Logger.log("账号", f"[{identifier}] 尝试签到...", "WAIT")
        status, msg = do_checkin(cookie, NS_RANDOM)
        
        if status == "success":
            result["status"] = "success"
            result["msg"] = msg
            Logger.log("账号", f"[{identifier}] ✓ {msg}", "OK")
            return result, cookie
        elif status == "already":
            result["status"] = "already"
            result["msg"] = msg
            Logger.log("账号", f"[{identifier}] ✓ {msg}", "OK")
            return result, cookie
        elif status != "invalid":
            # 其他错误但 cookie 可能有效
            result["status"] = status
            result["msg"] = msg
            Logger.log("账号", f"[{identifier}] {status}: {msg}", "WARN")
            return result, cookie
    
    # Cookie 无效，尝试登录
    if username and password:
        Logger.log("账号", f"[{identifier}] Cookie 无效，尝试登录...", "WARN")
        new_cookie = await login_and_get_cookie(username, password)
        
        if new_cookie:
            # 用新 cookie 签到
            status, msg = do_checkin(new_cookie, NS_RANDOM)
            result["status"] = status
            result["msg"] = msg
            
            if status in ["success", "already"]:
                Logger.log("账号", f"[{identifier}] ✓ {msg}", "OK")
            else:
                Logger.log("账号", f"[{identifier}] {status}: {msg}", "WARN")
            
            return result, new_cookie
        else:
            result["status"] = "login_failed"
            result["msg"] = "登录失败"
            Logger.log("账号", f"[{identifier}] 登录失败", "ERR")
            return result, None
    
    result["status"] = "no_credential"
    result["msg"] = "无有效凭证"
    return result, None

async def main():
    Logger.log("NodeSeek", "签到开始", "INFO")
    
    # 解析账号
    cookies_env = [c.strip() for c in NS_COOKIE.split('&') if c.strip()]
    accounts_env = [a.strip() for a in NS_ACCOUNTS.split('&') if a.strip()]
    
    # 加载保存的 cookies
    saved_cookies = load_cookies()
    
    # 合并账号信息
    accounts = {}
    
    # 从环境变量 cookie
    for i, cookie in enumerate(cookies_env):
        key = f"env_{i+1}"
        accounts[key] = {"cookie": cookie, "username": None, "password": None}
    
    # 从环境变量账号密码
    for acc in accounts_env:
        if ':' in acc:
            username, password = acc.split(':', 1)
            accounts[username] = {
                "cookie": saved_cookies.get(username),
                "username": username,
                "password": password
            }
    
    # 从保存的 cookies（可能是之前登录的）
    for key, cookie in saved_cookies.items():
        if key not in accounts:
            accounts[key] = {"cookie": cookie, "username": None, "password": None}
    
    if not accounts:
        Logger.log("NodeSeek", "未配置任何账号", "ERR")
        return
    
    Logger.log("NodeSeek", f"共 {len(accounts)} 个账号", "INFO")
    
    # 处理每个账号
    results = []
    new_cookies = {}
    
    for identifier, info in accounts.items():
        result, cookie = await process_account(
            identifier,
            info.get("cookie"),
            info.get("username"),
            info.get("password")
        )
        results.append(result)
        if cookie:
            new_cookies[identifier] = cookie
    
    # 保存更新的 cookies
    if new_cookies:
        save_cookies(new_cookies)
    
    # 汇总结果
    success = sum(1 for r in results if r["status"] in ["success", "already"])
    failed = len(results) - success
    
    summary = f"NodeSeek 签到完成\n成功: {success}/{len(results)}"
    for r in results:
        summary += f"\n• {r['id']}: {r['msg']}"
    
    Logger.log("NodeSeek", f"完成 - 成功 {success}/{len(results)}", "OK" if failed == 0 else "WARN")
    
    # 发送通知
    if TG_BOT_TOKEN:
        send_telegram(summary)

if __name__ == "__main__":
    asyncio.run(main())
