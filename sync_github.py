"""
建置最新 Liquidity & Sentiment 儀表板資料 (data.js) 並自動同步至 GitHub Pages
參考 00981a_tracker 的 SSH 免密碼推送架構 (git@github.com:mimiba0925/...)
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DASH_DIR = Path(__file__).resolve().parent


def run_cmd(cmd, check=True, capture=False):
    return subprocess.run(
        cmd,
        cwd=DASH_DIR,
        check=check,
        capture_output=capture,
        text=True,
    )


def main():
    print("=" * 65)
    print(" [Step 1/2] 執行 build_dashboard.py 產生最新 data.js ...")
    print("=" * 65)
    run_cmd([sys.executable, "build_dashboard.py"], check=True)

    print("\n" + "=" * 65)
    print(" [Step 2/2] 準備同步最新儀表板至 GitHub Pages ...")
    print("=" * 65)

    # 檢查是否已設定 remote origin
    rem = run_cmd(["git", "remote", "-v"], check=False, capture=True)
    if "origin" not in (rem.stdout or ""):
        print("⚠️ 尚未綁定 GitHub 遠端倉庫 (remote origin)。")
        print("請先在 GitHub 建立一個 Public 專案（例如 sentiment_liquidity_dashboard），然後執行：")
        print(f"  cd {DASH_DIR}")
        print("  git remote add origin git@github.com:mimiba0925/sentiment_liquidity_dashboard.git")
        print("  git push -u origin main")
        return 0

    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    run_cmd(["git", "add", "index.html", "styles.css", "app.js", "data.js", "build_dashboard.py", "indicator_config.py", ".gitignore"], check=True)

    commit_res = run_cmd(
        ["git", "commit", "-m", f"Auto update dashboard: {today_str}"],
        check=False,
        capture=True,
    )
    combined = (commit_res.stdout or "") + (commit_res.stderr or "")
    if "nothing to commit" in combined:
        print("ℹ️ 資料無新變動，略過 commit。")
    else:
        print("✔ git commit 完成")

    run_cmd(["git", "push", "origin", "main"], check=True)
    print("✅ 成功同步最新 Liquidity & Sentiment Dashboard 至 GitHub Pages！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
