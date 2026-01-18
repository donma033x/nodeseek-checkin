#!/usr/bin/env python3
"""
NodeSeek & DeepFlood 论坛自动签到脚本

cron: 0 9 * * *
new Env('nodeseek-checkin')

环境变量:
    NODESEEK_COOKIE: NodeSeek Cookie
    NODESEEK_ACCOUNT: NodeSeek 账号密码 (user:pass)
    DEEPFLOOD_COOKIE: DeepFlood Cookie（可选，不设置则自动通过 OAuth 获取）
    NODESEEK_RANDOM: 是否随机签到 true/false（默认 true）
    YESCAPTCHA_API_KEY: YesCaptcha API Key（用于解决 Turnstile）
    TELEGRAM_BOT_TOKEN: Telegram 通知（可选）
    TELEGRAM_CHAT_ID: Telegram 聊天ID（可选）

说明:
    DeepFlood Cookie 有效期 30 天，建议设置 DEEPFLOOD_COOKIE 避免每次 OAuth
    Cookie 失效时会自动通过 NodeSeek OAuth 重新获取
"""

import os
import sys
import json
import re
import asyncio
import time
import requests as http_requests
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================
NODESEEK_COOKIE = os.environ.get('NODESEEK_COOKIE', '')
NODESEEK_ACCOUNT = os.environ.get('NODESEEK_ACCOUNT', '')
DEEPFLOOD_COOKIE = os.environ.get('DEEPFLOOD_COOKIE', '')
NODESEEK_RANDOM = os.environ.get('NODESEEK_RANDOM', 'true').lower() == 'true'
YESCAPTCHA_KEY = os.environ.get('YESCAPTCHA_KEY', '') or os.environ.get('YESCAPTCHA_API_KEY', '')
TG_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

TURNSTILE_SITEKEY = "0x4AAAAAAAaNy7leGjewpVyR"
NODESEEK_SIGNIN_URL = "https://www.nodeseek.com/signIn.html"

# 站点配置
SITES = {
    "NodeSeek": {
        "base_url": "https://www.nodeseek.com",
        "attendance_url": "https://www.nodeseek.com/api/attendance",
        "origin": "https://www.nodeseek.com",
        "referer": "https://www.nodeseek.com/board",
    },
    "DeepFlood": {
        "base_url": "https://www.deepflood.com",
        "attendance_url": "https://www.deepflood.com/api/attendance",
        "origin": "https://www.deepflood.com",
        "referer": "https://www.deepflood.com/board",
        "oauth_url": "https://www.deepflood.com/api/account/nodeseek-signIn",
    }
}

# ==================== 日志 ====================
class Logger:
    @staticmethod
    def log(tag, msg, icon="ℹ"):
        icons = {"OK": "✓", "WARN": "⚠", "WAIT": "⏳", "INFO": "ℹ", "ERR": "✗"}
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] [{tag}] {icons.get(icon, icon)} {msg}")

# ==================== 青龙环境变量更新 ====================
def update_ql_env(name, value, remarks=""):
    """更新青龙环境变量（通过修改 config.sh）"""
    config_file = Path("/ql/data/config/config.sh")
    if not config_file.exists():
        Logger.log("青龙", "config.sh 不存在，跳过更新", "WARN")
        return False
    
    try:
        with open(config_file, 'r') as f:
            content = f.read()
        
        escaped_value = value.replace('"', '\\"')
        new_line = f'export {name}="{escaped_value}"'
        
        pattern = rf'^export {name}=.*$'
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            content += f"\n{new_line}\n"
        
        with open(config_file, 'w') as f:
            f.write(content)
        
        Logger.log("青龙", f"环境变量 {name} 已更新", "OK")
        return True
    except Exception as e:
        Logger.log("青龙", f"更新异常: {e}", "WARN")
        return False

# ==================== YesCaptcha Turnstile 解决 ====================
def solve_turnstile_yescaptcha():
    """使用 YesCaptcha 解决 Turnstile"""
    if not YESCAPTCHA_KEY:
        return None
    
    Logger.log("Turnstile", "使用 YesCaptcha...", "WAIT")
    try:
        r = http_requests.post("https://api.yescaptcha.com/createTask", json={
            "clientKey": YESCAPTCHA_KEY,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": NODESEEK_SIGNIN_URL,
                "websiteKey": TURNSTILE_SITEKEY
            }
        }, timeout=30)
        data = r.json()
        if data.get('errorId'):
            Logger.log("Turnstile", f"创建任务失败: {data.get('errorDescription')}", "WARN")
            return None
        task_id = data.get('taskId')
        
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

# ==================== DeepFlood OAuth 登录 ====================
def get_deepflood_cookie(nodeseek_cookie):
    """使用 NodeSeek Cookie 通过 OAuth 获取 DeepFlood Cookie"""
    try:
        from curl_cffi import requests
    except ImportError:
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    Logger.log("DeepFlood", "通过 NodeSeek OAuth 获取 Cookie...", "WAIT")
    
    try:
        # 1. 从 NodeSeek 获取 cAuth 数据
        ns_headers = {
            'Cookie': nodeseek_cookie,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
            'Referer': 'https://www.nodeseek.com/connect?target=DeepFlood',
            'Origin': 'https://www.nodeseek.com'
        }
        
        resp = requests.get(
            'https://www.nodeseek.com/api/cAuth?target=DeepFlood',
            headers=ns_headers,
            impersonate='safari15_5',
            timeout=30
        )
        
        if resp.status_code == 403:
            Logger.log("DeepFlood", "cAuth 被 Cloudflare 拦截 (403)", "WARN")
            return None
        
        auth_data = resp.json()
        if not auth_data.get('success'):
            msg = auth_data.get('message', str(auth_data))
            if '10次' in msg:
                Logger.log("DeepFlood", "NodeSeek Connect 次数已用完，请明天再试或手动设置 DEEPFLOOD_COOKIE", "WARN")
            else:
                Logger.log("DeepFlood", f"cAuth 失败: {msg}", "WARN")
            return None
        
        # 2. 发送到 DeepFlood 完成登录
        df_session = requests.Session(impersonate='safari15_5')
        df_session.get('https://www.deepflood.com/', headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15'
        })
        
        login_data = {
            "data": auth_data['data'],
            "wtf": auth_data['wtf'],
            "sign": auth_data['sign']
        }
        
        df_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
            'Referer': 'https://www.deepflood.com/nsSignIn.html',
            'Origin': 'https://www.deepflood.com',
            'Content-Type': 'application/json'
        }
        
        resp2 = df_session.post(
            'https://www.deepflood.com/api/account/nodeseek-signIn',
            json=login_data,
            headers=df_headers,
            timeout=30
        )
        
        result = resp2.json()
        if not result.get('success'):
            Logger.log("DeepFlood", f"OAuth 登录失败: {result}", "WARN")
            return None
        
        # 3. 获取 Cookie
        cookies = df_session.cookies.get_dict()
        if cookies:
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            Logger.log("DeepFlood", "OAuth 登录成功", "OK")
            return cookie_str
        
        return None
    except Exception as e:
        Logger.log("DeepFlood", f"OAuth 异常: {e}", "ERR")
        return None

# ==================== 签到（使用 curl_cffi）====================
def do_checkin(cookie, site_name, random=True):
    """对指定站点执行签到"""
    try:
        from curl_cffi import requests
    except ImportError:
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    site = SITES[site_name]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15',
        'origin': site["origin"],
        'referer': site["referer"],
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    
    url = f"{site['attendance_url']}?random={'true' if random else 'false'}"
    
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
    """使用 API 登录 NodeSeek"""
    try:
        from curl_cffi import requests
    except ImportError:
        os.system("pip install curl_cffi -q")
        from curl_cffi import requests
    
    session = requests.Session(impersonate='safari15_5')
    session.get(NODESEEK_SIGNIN_URL)
    
    data = {
        "username": username,
        "password": password,
        "token": turnstile_token,
        "source": "turnstile"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
        'origin': 'https://www.nodeseek.com',
        'referer': NODESEEK_SIGNIN_URL,
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
    """处理单个账号，签到 NodeSeek 和 DeepFlood"""
    results = []
    ns_cookie = cookie
    df_cookie = None
    
    # 如果没有 cookie，先登录
    if not ns_cookie and username and password:
        Logger.log("账号", f"[{identifier}] 无 Cookie，登录...", "WAIT")
        token = solve_turnstile_yescaptcha()
        if not token:
            return [{"site": "NodeSeek", "status": "turnstile_failed", "msg": "Turnstile 验证失败"}], None
        
        ns_cookie = login_with_api(username, password, token)
        if not ns_cookie:
            return [{"site": "NodeSeek", "status": "login_failed", "msg": "登录失败"}], None
        
        Logger.log("账号", f"[{identifier}] 登录成功", "OK")
    
    if not ns_cookie:
        return [{"site": "All", "status": "no_credential", "msg": "无有效凭证"}], None
    
    # NodeSeek 签到
    Logger.log("NodeSeek", f"[{identifier}] 签到中...", "WAIT")
    status, msg = do_checkin(ns_cookie, "NodeSeek", NODESEEK_RANDOM)
    results.append({"site": "NodeSeek", "status": status, "msg": msg})
    
    if status in ["success", "already"]:
        Logger.log("NodeSeek", f"[{identifier}] ✓ {msg}", "OK")
    elif status == "invalid":
        Logger.log("NodeSeek", f"[{identifier}] Cookie 无效", "WARN")
        # Cookie 无效，尝试重新登录
        if username and password:
            Logger.log("账号", f"[{identifier}] 重新登录...", "WAIT")
            token = solve_turnstile_yescaptcha()
            if token:
                ns_cookie = login_with_api(username, password, token)
                if ns_cookie:
                    Logger.log("账号", f"[{identifier}] 登录成功", "OK")
                    status, msg = do_checkin(ns_cookie, "NodeSeek", NODESEEK_RANDOM)
                    results[-1] = {"site": "NodeSeek", "status": status, "msg": msg}
                    if status in ["success", "already"]:
                        Logger.log("NodeSeek", f"[{identifier}] ✓ {msg}", "OK")
    else:
        Logger.log("NodeSeek", f"[{identifier}] {status}: {msg}", "WARN")
    
    # DeepFlood 签到
    Logger.log("DeepFlood", f"[{identifier}] 签到中...", "WAIT")
    
    df_cookie = DEEPFLOOD_COOKIE
    new_df_cookie = None
    
    # 如果有 DEEPFLOOD_COOKIE，先尝试使用
    if df_cookie:
        status, msg = do_checkin(df_cookie, "DeepFlood", NODESEEK_RANDOM)
    else:
        # 没有 DEEPFLOOD_COOKIE，先尝试 NodeSeek Cookie
        status, msg = do_checkin(ns_cookie, "DeepFlood", NODESEEK_RANDOM)
    
    # Cookie 无效时，通过 OAuth 获取新的 DeepFlood Cookie
    if status == "invalid" or (status == "fail" and "403" in str(msg)):
        Logger.log("DeepFlood", "Cookie 无效，通过 OAuth 重新获取...", "WAIT")
        new_df_cookie = get_deepflood_cookie(ns_cookie)
        if new_df_cookie:
            status, msg = do_checkin(new_df_cookie, "DeepFlood", NODESEEK_RANDOM)
            if status in ["success", "already"]:
                # 更新环境变量
                update_ql_env("DEEPFLOOD_COOKIE", new_df_cookie)
    
    results.append({"site": "DeepFlood", "status": status, "msg": msg})
    
    if status in ["success", "already"]:
        Logger.log("DeepFlood", f"[{identifier}] ✓ {msg}", "OK")
    else:
        Logger.log("DeepFlood", f"[{identifier}] {status}: {msg}", "WARN")
    
    return results, ns_cookie

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
    Logger.log("签到", "NodeSeek & DeepFlood 签到开始", "INFO")
    
    # 解析账号
    accounts = {}
    
    if NODESEEK_ACCOUNT:
        for acc in NODESEEK_ACCOUNT.split('&'):
            acc = acc.strip()
            if ':' in acc:
                username, password = acc.split(':', 1)
                accounts[username.strip()] = {
                    "username": username.strip(),
                    "password": password.strip(),
                    "cookie": None
                }
    
    # 如果有 Cookie
    if NODESEEK_COOKIE:
        if accounts:
            # 把 cookie 关联到第一个账号
            first_key = list(accounts.keys())[0]
            accounts[first_key]["cookie"] = NODESEEK_COOKIE
        else:
            accounts["默认账号"] = {"username": None, "password": None, "cookie": NODESEEK_COOKIE}
    
    if not accounts:
        Logger.log("签到", "未配置任何账号，请设置 NODESEEK_COOKIE 或 NODESEEK_ACCOUNT", "ERR")
        return
    
    Logger.log("签到", f"共 {len(accounts)} 个账号", "INFO")
    
    all_results = []
    final_cookie = None
    
    for identifier, info in accounts.items():
        results, cookie = await process_account(
            identifier,
            info.get("cookie"),
            info.get("username"),
            info.get("password")
        )
        all_results.extend(results)
        if cookie:
            final_cookie = cookie
    
    # 更新环境变量
    if final_cookie:
        update_ql_env("NODESEEK_COOKIE", final_cookie)
    
    # 统计结果
    ns_success = sum(1 for r in all_results if r["site"] == "NodeSeek" and r["status"] in ["success", "already"])
    df_success = sum(1 for r in all_results if r["site"] == "DeepFlood" and r["status"] in ["success", "already"])
    
    summary = f"签到完成\nNodeSeek: {'✓' if ns_success else '✗'}\nDeepFlood: {'✓' if df_success else '✗'}"
    for r in all_results:
        summary += f"\n• {r['site']}: {r['msg']}"
    
    total_success = ns_success + df_success
    total = len([r for r in all_results if r["site"] in ["NodeSeek", "DeepFlood"]])
    Logger.log("签到", f"完成 - {total_success}/{total} 成功", "OK" if total_success == total else "WARN")
    
    if TG_BOT_TOKEN:
        send_telegram(summary)

if __name__ == "__main__":
    asyncio.run(main())
