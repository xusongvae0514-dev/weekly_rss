import os
import re
import requests
from datetime import datetime, timezone
from feedgen.feed import FeedGenerator

OWNER = "xuanli199"
REPO = "weekly"
DOCS_DIR = "docs"
BRANCH = "main"

API_BASE = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json"
}
# 动态注入 GitHub Actions 的 token，提升 API 额度并避免限流
GH_TOKEN = os.environ.get("GH_TOKEN")
if GH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GH_TOKEN}"

def get_docs_list():
    # 列出 docs/ 目录文件
    url = f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{DOCS_DIR}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    files = r.json()
    md = [f for f in files if f.get("type") == "file" and f.get("name","").lower().endswith(".md")]
    return md

def get_latest_commit_for_file(path):
    # 拿到文件的最近一次提交（用于 pubDate）
    url = f"{API_BASE}/repos/{OWNER}/{REPO}/commits"
    params = {"path": path, "per_page": 1, "sha": BRANCH}
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data:
        c = data[0]
        # 取 author.date 或 committer.date
        date_str = c.get("commit", {}).get("author", {}).get("date") or c.get("commit", {}).get("committer", {}).get("date")
        if date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return None

def md_to_summary(md_text, max_chars=400):
    # 简易 Markdown -> 文本摘要（保留前几行内容，去掉链接语法等）
    text = md_text.strip()
    # 把 [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 去掉图片语法 ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # 去掉前置标题符号
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    # 压缩多余空行
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    summary = " ".join(lines[:12])  # 取前若干行
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "..."
    return summary

def main():
    docs = get_docs_list()

    # 获取每个文件的最近提交时间并排序（新→旧）
    enriched = []
    for f in docs:
        rel_path = f"{DOCS_DIR}/{f['name']}"
        commit_dt = get_latest_commit_for_file(rel_path) or datetime.now(timezone.utc)
        enriched.append({
            "name": f["name"],
            "html_url": f["html_url"],          # GitHub 上的文件网页
            "download_url": f.get("download_url"), # 原始内容
            "commit_dt": commit_dt,
        })
    enriched.sort(key=lambda x: x["commit_dt"], reverse=True)

    fg = FeedGenerator()
    fg.id(f"https://github.com/{OWNER}/{REPO}/tree/{BRANCH}/{DOCS_DIR}")
    fg.title("玄离199 每周科技补全 - 文本版 RSS")
    fg.link(href=f"https://github.com/{OWNER}/{REPO}/tree/{BRANCH}/{DOCS_DIR}", rel="alternate")
    fg.description("自动生成的 RSS Feed（来源：docs/ 目录），包含最近若干期，带提交时间与内容摘要。")
    fg.language("zh-cn")
    fg.ttl(720)  # 建议缓存 12 小时

    # 生成最近 12 条
    for item in enriched[:12]:
        content = ""
        if item["download_url"]:
            try:
                r = requests.get(item["download_url"], headers=HEADERS, timeout=30)
                if r.ok:
                    content = md_to_summary(r.text)
            except Exception:
                content = ""
        title = item["name"].replace(".md", "")
        fe = fg.add_entry()
        fe.id(item["html_url"])
        fe.title(title)
        fe.link(href=item["html_url"])
        if content:
            fe.description(content)
        fe.published(item["commit_dt"])

    os.makedirs("public", exist_ok=True)
    fg.rss_file("public/weekly.xml", pretty=True)
    print("✅ RSS 生成完成：public/weekly.xml")

if __name__ == "__main__":
    main()
