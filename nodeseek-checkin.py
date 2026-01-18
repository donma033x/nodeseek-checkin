#!/usr/bin/env python3
"""
NodeSeek 论坛自动签到脚本

cron: 0 9 * * *
new Env('nodeseek-checkin')

环境变量:
    NS_COOKIE: Cookie（多账号用 & 分隔）
    NS_ACCOUNTS: 账号密码 email:password（多账号用 & 分隔）
    NS_RANDOM: 是否随机签到 true/false（默认 true）
    YESCAPTCHA_KEY: YesCaptcha API Key（用于解决 Turnstile）
    TELEGRAM_BOT_TOKEN: Telegram 通知（可选）
    TELEGRAM_CHAT_ID: Telegram 聊天ID（可选）
"""

import os
import sys
import json
import asyncio
import time
import requests as http_requests
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================
NS_COOKIE = os.environ.get('NS_COOKIE', '')
NS_ACCOUNTS = os.environ.get('NS_ACCOUNTS', '')
NS_RANDOM = os.environ.get('NS_RANDOM', 'true').lower() == 'true'
YESCAPTCHA_KEY = os.environ.get('YESCAPTCHA_KEY', '')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

COOKIE_FILE = Path(__file__).parent / "cookies.json"
TURNSTILE_SITEKEY = "0x4AAAAAAAaNy7leGjewpVyR"
SIGNIN_URL = "https://www.nodeseek.com/signIn.html"

# ==================== 日志 ====================
class Logger:
    @staticmethod
    def log(tag, msg, icon="ℹ"):
        icons = {"OK": "✓", "WARN": "⚠", "WAIT": "⏳", "INFO": "ℹ", "ERR": "✗"}
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] [{tag}] {icons.get(icon, icon)} {msg}")

# ==================== Cookie 管理 ====================
def load_cookies():
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_cookies(cookies_dict):
    with open(COOKIE_FILE, 'w') as f:
        json.dump(cookies_dict, f, indent=2)
    Logger.log("Cookie", f"已保存 {len(cookies_dict)} 个账号", "OK")

# ==================== YesCaptcha Turnstile 解决 ====================
def solve_turnstile_yescaptcha():
    """使用 YesCaptcha 解决 Turnstile"""
    if not YESCAPTCHA_KEY:
        return None
    
    Logger.log("Turnstile", "使用 YesCaptcha...", "WAIT")
    try:
        # 创建任务
        r = http_requests.post("https://api.yescaptcha.com/createTask", json={
            "clientKey": YESCAPTCHA_KEY,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": SIGNIN_URL,
                "websiteKey": TURNSTILE_SITEKEY
            }
        }, timeout=30)
        data = r.json()
        if data.get('errorId'):
            Logger.log("Turnstile", f"创建任务失败: {data.get('errorDescription')}", "WARN")
            return None
        task_id = data.get('taskId')
        
        # 轮询结果
        for i in range(40):
            time.sleep(3)
            r = http_requests.post("https://api.yescaptcha.com/getTaskResult", json={
                "clientKey": YESCAPTCHA_KEY,
                "taskId": task_id
            }, timeout=30)
            result = r.json()
            if result.get('status') == 'ready':
                token = result.get('solution', {}).get('token')
                Logger.log("Turnstile", f"验证成功 ({(i+1)*3}s)", "OK")
                return token
        
        Logger.log("Turnstile", "超时", "WARN")
        return None
    except Exception as e:
        Logger.log("Turnstile", f"错误: {e}", "ERR")
        return None

# ==================== 签到（使用 curl_cffi）====================
def do_checkin(cookie, random=True):
    try:
        from curl_cffi import requests
    except ImportError:
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15',
        'origin': 'https://www.nodeseek.com',
        'referer': 'https://www.nodeseek.com/board',
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    
    url = f"https://www.nodeseek.com/api/attendance?random={'true' if random else 'false'}"
    
    for imp in ['safari15_5', 'safari15_3', 'chrome120', 'chrome119']:
        try:
            resp = requests.post(url, headers=headers, json={}, impersonate=imp, timeout=30)
            if resp.status_code == 403 and "challenge" in resp.text.lower():
                continue
            
            data = resp.json()
            msg = data.get("message", "")
            
            if "鸡腿" in msg or data.get("success"):
                return "success", msg
            elif "已完成签到" in msg:
                return "already", msg
            elif data.get("status") == 404:
                return "invalid", msg
            return "fail", msg
        except Exception as e:
            continue
    
    return "error", "请求失败"

# ==================== 登录获取 Cookie ====================
def login_with_api(username, password, turnstile_token):
    """使用 API 登录"""
    try:
        from curl_cffi import requests
    except ImportError:
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    session = requests.Session(impersonate='safari15_5')
    
    # 先访问登录页获取初始 cookie
    session.get(SIGNIN_URL)
    
    # 登录
    data = {
        "username": username,
        "password": password,
        "token": turnstile_token,
        "source": "turnstile"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
        'origin': 'https://www.nodeseek.com',
        'referer': SIGNIN_URL,
        'Content-Type': 'application/json'
    }
    
    resp = session.post("https://www.nodeseek.com/api/account/signIn", json=data, headers=headers)
    result = resp.json()
    
    if result.get("success"):
        cookies = session.cookies.get_dict()
        cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        return cookie_str
    else:
        Logger.log("登录", f"失败: {result.get('message')}", "ERR")
        return None

# ==================== 主流程 ====================
async def process_account(identifier, cookie=None, username=None, password=None):
    result = {"id": identifier, "status": "", "msg": ""}
    
    # 先尝试用 cookie 签到
    if cookie:
        Logger.log("账号", f"[{identifier}] 签到中...", "WAIT")
        status, msg = do_checkin(cookie, NS_RANDOM)
        
        if status in ["success", "already"]:
            result["status"] = status
            result["msg"] = msg
            Logger.log("账号", f"[{identifier}] ✓ {msg}", "OK")
            return result, cookie
        elif status != "invalid":
            result["status"] = status
            result["msg"] = msg
            return result, cookie
    
    # Cookie 无效，尝试登录
    if username and password:
        Logger.log("账号", f"[{identifier}] Cookie 无效，登录...", "WARN")
        
        # 解决 Turnstile
        token = solve_turnstile_yescaptcha()
        if not token:
            result["status"] = "turnstile_failed"
            result["msg"] = "Turnstile 验证失败，请配置 YESCAPTCHA_KEY"
            return result, None
        
        # 登录
        new_cookie = login_with_api(username, password, token)
        if new_cookie:
            Logger.log("账号", f"[{identifier}] 登录成功", "OK")
            
            # 签到
            status, msg = do_checkin(new_cookie, NS_RANDOM)
            result["status"] = status
            result["msg"] = msg
            
            if status in ["success", "already"]:
                Logger.log("账号", f"[{identifier}] ✓ {msg}", "OK")
            
            return result, new_cookie
        else:
            result["status"] = "login_failed"
            result["msg"] = "登录失败"
            return result, None
    
    result["status"] = "no_credential"
    result["msg"] = "无有效凭证"
    return result, None

def send_telegram(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass

async def main():
    Logger.log("NodeSeek", "签到开始", "INFO")
    
    cookies_env = [c.strip() for c in NS_COOKIE.split('&') if c.strip()]
    accounts_env = [a.strip() for a in NS_ACCOUNTS.split('&') if a.strip()]
    saved_cookies = load_cookies()
    
    accounts = {}
    
    for i, cookie in enumerate(cookies_env):
        key = f"env_{i+1}"
        accounts[key] = {"cookie": cookie, "username": None, "password": None}
    
    for acc in accounts_env:
        if ':' in acc:
            username, password = acc.split(':', 1)
            accounts[username] = {
                "cookie": saved_cookies.get(username),
                "username": username,
                "password": password
            }
    
    for key, cookie in saved_cookies.items():
        if key not in accounts:
            accounts[key] = {"cookie": cookie, "username": None, "password": None}
    
    if not accounts:
        Logger.log("NodeSeek", "未配置任何账号", "ERR")
        return
    
    Logger.log("NodeSeek", f"共 {len(accounts)} 个账号", "INFO")
    
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
    
    if new_cookies:
        save_cookies(new_cookies)
    
    success = sum(1 for r in results if r["status"] in ["success", "already"])
    
    summary = f"NodeSeek 签到完成\n成功: {success}/{len(results)}"
    for r in results:
        summary += f"\n• {r['id']}: {r['msg']}"
    
    Logger.log("NodeSeek", f"完成 - 成功 {success}/{len(results)}", "OK" if success == len(results) else "WARN")
    
    if TG_BOT_TOKEN:
        send_telegram(summary)

if __name__ == "__main__":
    asyncio.run(main())
