"""
济南仪表盘 — 一键部署
- 有 Netlify 配置 → API 自动部署到固定网址
- 无配置 → 打开 Netlify Drop 手动拖拽
"""
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
RELEASE_DIR = ROOT / "release"
CONVERT = ROOT / "convert.py"
INDEX = ROOT / "index.html"
CONFIG_FILE = ROOT / ".netlify-config.json"

DATA_FILES = ["daily.json", "weekly.json", "monthly.json"]
NETLIFY_API = "https://api.netlify.com/api/v1"
NETLIFY_DROP = "https://app.netlify.com/drop"


def ensure_exists(path: Path, label: str):
    if not path.exists():
        raise FileNotFoundError(f"找不到{label}：{path}")


def run_step(title: str, command: list[str]):
    print(f"\n{title}")
    print("-" * 50)
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"{title}失败，退出码：{result.returncode}")


def build_release():
    """复制静态文件到 release 文件夹"""
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(INDEX, RELEASE_DIR / "index.html")
    print(f"  ✓ index.html")

    release_data = RELEASE_DIR / "data"
    release_data.mkdir(exist_ok=True)
    for fname in DATA_FILES:
        src = DATA_DIR / fname
        if src.exists():
            shutil.copy2(src, release_data / fname)
            size_kb = src.stat().st_size / 1024
            print(f"  ✓ data/{fname} ({size_kb:.1f} KB)")
        else:
            print(f"  ⚠ data/{fname} 不存在，跳过")

    print(f"\n✅ 发布包已生成: {RELEASE_DIR}")


def netlify_api_request(token: str, method: str, path: str, data=None, content_type=None):
    """调用 Netlify API"""
    url = NETLIFY_API + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "JinanDashboard/1.0")

    body = None
    if data is not None:
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data
            if content_type:
                req.add_header("Content-Type", content_type)

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, data=body, context=ctx, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ API 错误 [{e.code}]: {err_body[:300]}")
        return None


def deploy_to_netlify(config: dict):
    """通过 Netlify API 自动部署"""
    token = config["token"]
    site_id = config["site_id"]
    site_url = config.get("site_url", "")

    print(f"\n🚀 正在部署到: {site_url}")

    # 1. 创建 zip
    print("   📦 打包文件...")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in RELEASE_DIR.rglob("*"):
            if f.is_file():
                arcname = str(f.relative_to(RELEASE_DIR)).replace("\\", "/")
                zf.write(f, arcname)

    zip_size = os.path.getsize(zip_path) / 1024
    print(f"   📦 包大小: {zip_size:.1f} KB")

    try:
        # 2. 上传部署
        print("   📤 上传到 Netlify...")
        zip_data = Path(zip_path).read_bytes()
        result = netlify_api_request(
            token, "POST",
            f"/sites/{site_id}/deploys",
            data=zip_data,
            content_type="application/zip"
        )

        if not result:
            raise RuntimeError("部署请求失败")

        deploy_id = result.get("id", "")
        deploy_state = result.get("state", "")
        deploy_url = result.get("deploy_ssl_url") or result.get("deploy_url", "")

        if deploy_state == "error":
            error_msg = result.get("error_message", "未知错误")
            raise RuntimeError(f"部署失败: {error_msg}")

        print(f"\n   ✅ 部署成功!")
        print(f"   🔗 {site_url}")
        print(f"   📋 部署ID: {deploy_id}")

        # 3. 发布（publish the deploy to production）
        if deploy_id:
            print("   🏷️  发布到生产环境...")
            pub = netlify_api_request(
                token, "POST",
                f"/sites/{site_id}/deploys/{deploy_id}/restore"
            )
            if pub:
                print(f"   ✅ 已发布")

    finally:
        # 清理临时 zip
        try:
            os.unlink(zip_path)
        except OSError:
            pass

    return site_url


def main():
    print("=" * 50)
    print("  济南区域 · 销售数据监督仪表盘")
    print("  一键部署")
    print("=" * 50)

    ensure_exists(CONVERT, "convert.py")
    ensure_exists(INDEX, "index.html")
    ensure_exists(DATA_DIR, "data/ 文件夹")

    # Step 1: 刷新数据
    run_step("[1/2] 刷新数据（convert.py）",
             [sys.executable, str(CONVERT)])

    # Step 2: 构建发布包
    print("\n[2/2] 构建发布包")
    print("-" * 50)
    build_release()

    # Step 3: 部署
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text("utf-8"))
            if config.get("token") and config.get("site_id"):
                print("\n[3/3] 自动部署到固定网址")
                print("-" * 50)
                url = deploy_to_netlify(config)
                print("\n" + "=" * 50)
                print(f"  ✅ 部署完成！固定网址: {url}")
                print("=" * 50)
                return
        except Exception as e:
            print(f"\n⚠️  自动部署失败: {e}")
            print("   回退到手动上传...")

    # 回退：打开 Netlify Drop
    print(f"\n📤 打开 Netlify Drop 上传页面...")
    print(f"   {NETLIFY_DROP}")
    webbrowser.open(NETLIFY_DROP)

    print("\n" + "=" * 50)
    print("  下一步：")
    print(f"  1. 浏览器已打开 Netlify Drop")
    print(f"  2. 拖入文件夹: {RELEASE_DIR}")
    print(f"  3. 复制固定网址 → 分享")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n[ERROR] 部署失败：{error}")
        sys.exit(1)
