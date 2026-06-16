#!/usr/bin/env python3
"""Netlify 一键设置 — 创建固定站点，仅需运行一次"""
import json, os, sys, ssl, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / ".netlify-config.json"

NETLIFY_API = "https://api.netlify.com/api/v1"

print("=" * 50)
print("  Netlify 固定站点 · 一次性设置")
print("=" * 50)
print()
print("需要你的 Netlify Personal Access Token，获取方式：")
print("  1. 打开 https://app.netlify.com/user/applications/personal")
print("  2. 点击「New access token」")
print("  3. 复制 token 粘贴到下面")
print()


def api_request(method, path, token, data=None, content_type=None):
    url = NETLIFY_API + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "JinanDashboard/1.0")
    if content_type:
        req.add_header("Content-Type", content_type)
    
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode("utf-8")
    
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, data=body, context=ctx, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ API 错误 [{e.code}]: {err}")
        return None


# Step 1: Get token
if CONFIG_FILE.exists():
    config = json.loads(CONFIG_FILE.read_text("utf-8"))
    token = config.get("token", "")
    if token:
        reuse = input(f"已有配置 (站点: {config.get('site_name','?')})，重用 token？[Y/n]: ").strip().lower()
        if reuse in ("", "y", "yes"):
            print("✅ 使用已有 token")
        else:
            token = ""

if not token:
    token = input("粘贴 Netlify Access Token: ").strip()
    if not token:
        print("❌ token 不能为空")
        sys.exit(1)

# Step 2: Verify token
print("\n🔍 验证 token...")
user = api_request("GET", "/user", token)
if not user:
    print("❌ token 无效，请检查")
    sys.exit(1)
print(f"✅ 已登录: {user.get('full_name') or user.get('email')}")

# Step 3: Create site
site_name = "jinan-dashboard"
print(f"\n📦 创建站点: {site_name}...")

# Check if site already exists
sites = api_request("GET", "/sites", token)
existing = None
if sites:
    for s in sites:
        if s.get("name") == site_name:
            existing = s
            break

if existing:
    site_id = existing["id"]
    site_url = existing.get("ssl_url") or existing.get("url", "")
    print(f"⚠️  站点已存在: {site_url}")
else:
    result = api_request("POST", "/sites", token, data={
        "name": site_name,
    })
    if not result:
        print("❌ 创建站点失败")
        sys.exit(1)
    site_id = result["id"]
    site_url = result.get("ssl_url") or result.get("url", "")
    print(f"✅ 站点已创建!")

# Step 4: Save config
config = {
    "token": token,
    "site_id": site_id,
    "site_name": site_name,
    "site_url": site_url,
}
CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), "utf-8")
os.chmod(CONFIG_FILE, 0o600)  # restrict permissions

print(f"""
{'='*50}
  ✅ 设置完成！

  固定网址: {site_url}
  配置已保存: {CONFIG_FILE}

  以后只需跟我说「阿龙，更新发布济南仪表盘」
  我会自动刷新数据并部署到这个固定网址！
{'='*50}
""")
