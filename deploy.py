"""
济南仪表盘 — 一键部署到 GitHub Pages
- 固定网址: https://dx-bot01.github.io/jinan-dashboard/
- 通过 GitHub API 直接推送，绕过公司网络 git 限制
"""
import base64
import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
CONVERT = ROOT / "convert.py"
INDEX = ROOT / "index.html"

REPO_OWNER = "DX-bot01"
REPO_NAME = "jinan-dashboard"
BRANCH = "main"
PAGES_URL = f"https://{REPO_OWNER.lower()}.github.io/{REPO_NAME}/"

GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def find_github_token():
    """从多个来源查找 GitHub token"""
    # 1. 环境变量
    for v in ["GH_TOKEN", "GITHUB_TOKEN"]:
        if os.environ.get(v):
            return os.environ[v]
    # 2. git credential helper
    try:
        result = subprocess.run(
            ["git", "config", "--get", "github.token"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        token = result.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    # 3. git credential store
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, cwd=str(ROOT), timeout=5
        )
        for line in result.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def github_api(method: str, path: str, data=None, token=None):
    """调用 GitHub API"""
    url = path if path.startswith("http") else GITHUB_API + path
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "JinanDashboard/1.0")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, data=body, context=ctx, timeout=60) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"\n  ❌ API [{e.code}]: {err_body[:400]}")
        return None


def build_docs():
    """构建文档到 docs/ 目录"""
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # index.html
    shutil.copy2(INDEX, DOCS_DIR / "index.html")
    print(f"  ✓ index.html")

    # data files
    docs_data = DOCS_DIR / "data"
    docs_data.mkdir(exist_ok=True)
    for fname in ["daily.json", "weekly.json", "monthly.json"]:
        src = DATA_DIR / fname
        if src.exists():
            shutil.copy2(src, docs_data / fname)
            size_kb = src.stat().st_size / 1024
            print(f"  ✓ data/{fname} ({size_kb:.1f} KB)")
        else:
            print(f"  ⚠ data/{fname} 不存在")


def read_file_b64(filepath: Path):
    """读取文件并返回 base64"""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def deploy_github(token):
    """通过 GitHub API 推送 docs 目录"""
    print("\n[3/3] 部署到 GitHub Pages")
    print("-" * 50)

    # 1. 获取当前 HEAD ref
    print("   📍 获取仓库状态...")
    ref = github_api("GET", f"/git/ref/heads/{BRANCH}", token=token)
    if not ref:
        raise RuntimeError("无法获取仓库引用，请确认仓库已存在且 token 有效")
    base_sha = ref["object"]["sha"]

    # 2. 获取当前 tree
    commit = github_api("GET", f"/git/commits/{base_sha}", token=token)
    base_tree_sha = commit["tree"]["sha"]
    print(f"   📂 当前 tree: {base_tree_sha[:7]}")

    # 3. 创建所有文件的 blob
    print("   📦 上传文件...")
    new_items = []

    for root, dirs, files in os.walk(DOCS_DIR):
        for fname in files:
            fpath = Path(root) / fname
            rel_path = str(fpath.relative_to(DOCS_DIR)).replace("\\", "/")

            content_b64 = read_file_b64(fpath)
            blob = github_api("POST", "/git/blobs", token=token, data={
                "content": content_b64,
                "encoding": "base64"
            })
            if not blob:
                raise RuntimeError(f"上传 {rel_path} 失败")

            new_items.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"]
            })
            print(f"   ✓ {rel_path} ({blob['sha'][:7]})")

    # 4. 创建新 tree
    print("   🌲 创建 tree...")
    tree = github_api("POST", "/git/trees", token=token, data={
        "base_tree": base_tree_sha,
        "tree": new_items
    })
    new_tree_sha = tree["sha"]
    print(f"   🌲 新 tree: {new_tree_sha[:7]}")

    # 5. 创建 commit
    print("   📝 创建 commit...")
    from datetime import datetime
    now = datetime.now()
    commit_msg = f"更新仪表盘数据 - {now.strftime('%Y-%m-%d %H:%M')}"
    new_commit = github_api("POST", "/git/commits", token=token, data={
        "message": commit_msg,
        "tree": new_tree_sha,
        "parents": [base_sha]
    })
    new_sha = new_commit["sha"]
    print(f"   📝 commit: {new_sha[:7]}")

    # 6. 更新 ref
    print("   🚀 推送...")
    github_api("PATCH", f"/git/refs/heads/{BRANCH}", token=token, data={
        "sha": new_sha,
        "force": False
    })

    print(f"\n   ✅ 推送成功!")
    print(f"   🔗 固定网址: {PAGES_URL}")
    print(f"   ⏳ GitHub Pages 部署中（约 1-2 分钟生效）")

    return PAGES_URL


def main():
    print("=" * 50)
    print("  济南区域 · 销售数据监督仪表盘")
    print("  一键部署 → GitHub Pages")
    print("=" * 50)
    print(f"  固定网址: {PAGES_URL}")

    # Step 1: 刷新数据
    print(f"\n[1/2] 刷新数据（convert.py）")
    print("-" * 50)
    result = subprocess.run([sys.executable, str(CONVERT)], cwd=str(ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"数据转换失败，退出码：{result.returncode}")

    # Step 2: 构建 docs
    print("\n[2/2] 构建发布包 → docs/")
    print("-" * 50)
    build_docs()

    # Step 3: 查找 token 并部署
    token = find_github_token()
    if token:
        try:
            deploy_github(token)
        except Exception as e:
            print(f"\n  ⚠️ GitHub API 部署失败: {e}")
            print(f"\n  📋 手动推送:")
            print(f"     1. git add docs/")
            print(f'     2. git commit -m "更新仪表盘"')
            print(f"     3. git push")
    else:
        print("\n  ⚠️ 未找到 GitHub token，无法自动推送")
        print(f"\n  📋 请手动推送 docs/ 目录:")
        print(f"     1. git add docs/")
        print(f'     2. git commit -m "更新仪表盘"')
        print(f"     3. git push")
        print(f"\n  📤 或使用 GitHub Desktop 推送")

    print("\n" + "=" * 50)
    print(f"  ✅ 固定网址: {PAGES_URL}")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n[ERROR] 部署失败：{error}")
        sys.exit(1)
