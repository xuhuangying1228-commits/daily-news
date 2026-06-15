#!/usr/bin/env python3
"""美妆/科技行业日报 — GitHub Actions 定时推送飞书
数据来源：
  美妆：Google News 中文区 + 精选 RSS
  科技：Google News + IT之家/36氪/机器之心/量子位 + 推特 AI 圈
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
import re
from datetime import datetime
from xml.etree import ElementTree as ET


# ──────────────── 飞书 Webhook ────────────────
FEISHU_URL = os.environ["FEISHU_WEBHOOK_URL"]

# ──────────────── 通用请求头 ────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ──────────────── Google News RSS ────────────────
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"

GOOGLE_BEAUTY_QUERIES = [
    "美妆 化妆品 最新",
    "护肤 品牌 最新动态",
    "国货美妆 趋势",
    "化妆品行业 市场",
    "美容 护肤品 新规",
]

GOOGLE_TECH_QUERIES = [
    # AI 核心
    "AI 人工智能 最新进展 2026",
    "大模型 LLM GPT 发布",
    "AI Agent 智能体 应用",
    "具身智能 机器人 最新",
    "AI 开源模型 最新",
    "AI 芯片 算力 最新",
    # 行业
    "手机 新品 发布 2026",
    "芯片 半导体 最新",
    "人工智能 投融资 融资",
    "AI 生成式 应用 落地",
    "科技公司 AI 战略 2026",
]

# ──────────────── 中文 RSS 源 ────────────────
CHINESE_RSS_FEEDS = {
    "tech": [
        "https://www.ithome.com/rss/",
        "https://36kr.com/feed",
        "https://www.jiqizhixin.com/rss",
        "https://www.qbitai.com/rss",
    ],
    "beauty": [],
}

# ──────────────── Nitter 实例（推特 RSS） ────────────────
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

# 推特 AI 圈 KOL
TWITTER_AI_ACCOUNTS = [
    "sama",           # Sam Altman (OpenAI)
    "karpathy",       # Andrej Karpathy
    "ylecun",         # Yann LeCun (Meta AI)
    "AndrewYNg",      # Andrew Ng
    "jimfan",         # Jim Fan (NVIDIA)
]

# ──────────────── 主题配置 ────────────────
TOPIC_CONFIG = {
    "beauty": {
        "title_prefix": "💄 美妆行业日报",
        "sections": [
            ("📊 市场动态", "数据、业绩、规模"),
            ("🏭 行业事件", "品牌动态、合作、展会"),
            ("🔍 趋势洞察", "产品趋势、消费洞察、政策"),
        ],
        "google_queries": GOOGLE_BEAUTY_QUERIES,
        "rss_feeds": CHINESE_RSS_FEEDS["beauty"],
        "twitter": False,
        "footer": "💡 数据来源：12个公众号 + Google News中文区 | 每日9:00自动推送",
    },
    "tech": {
        "title_prefix": "🤖 AI·3C·科技日报",
        "sections": [
            ("📊 行业动态", "市场数据、行业趋势、投融资"),
            ("🏭 公司事件", "产品发布、企业动态、合作并购"),
            ("🔍 技术趋势", "AI突破、芯片进展、前沿技术"),
        ],
        "google_queries": GOOGLE_TECH_QUERIES,
        "rss_feeds": CHINESE_RSS_FEEDS["tech"],
        "twitter": True,
        "footer": "💡 来源：Google News + IT之家/36氪/机器之心/量子位 + 推特AI圈 | 精选10条 · 每日9:00自动推送",
    },
}


def fetch_url(url: str, timeout: int = 15) -> str | None:
    """获取URL内容"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ⚠ 请求失败 [{url[:60]}]: {e}", file=sys.stderr)
        return None


def parse_google_news_rss(xml_text: str) -> list[dict]:
    """解析 Google News RSS"""
    results = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = None
            link = None
            description = None
            for child in item:
                tag = child.tag.lower()
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                if tag == "title":
                    title = (child.text or "").strip()
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0]
                elif tag == "link":
                    link = (child.text or "").strip()
                elif tag == "description":
                    description = (child.text or "").strip()

            if title and link:
                # 清理 description 中的 HTML 标签
                clean_desc = description or ""
                clean_desc = re.sub(r"<[^>]+>", "", clean_desc).strip()
                results.append({
                    "title": title,
                    "href": link,
                    "body": clean_desc or title,
                })
    except ET.ParseError as e:
        print(f"  ⚠ RSS解析失败: {e}", file=sys.stderr)
    return results


def parse_rss(xml_text: str) -> list[dict]:
    """解析标准 RSS 2.0 / Atom"""
    results = []
    try:
        root = ET.fromstring(xml_text)

        # RSS 2.0: <channel><item>...
        items = root.iter("item")
        # 也尝试 Atom: <feed><entry>...
        if not list(root.iter("item")):
            items = root.iter("entry")

        for item in items:
            title = None
            link = None
            desc = None
            for child in item:
                tag = child.tag.lower()
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                if tag == "title":
                    title = (child.text or "").strip()
                elif tag == "link":
                    link = child.get("href") or (child.text or "").strip()
                elif tag in ("description", "summary", "content"):
                    txt = (child.text or "").strip()
                    if txt and len(txt) > len(desc or ""):
                        desc = txt

            if title and link and "http" in link:
                clean_desc = desc or title
                clean_desc = re.sub(r"<[^>]+>", "", clean_desc).strip()
                results.append({
                    "title": title,
                    "href": link,
                    "body": clean_desc[:120],
                })
    except ET.ParseError as e:
        print(f"  ⚠ RSS解析失败: {e}", file=sys.stderr)
    return results


def fetch_nitter_rss(account: str, timeout: int = 10) -> list[dict]:
    """从 Nitter 抓取推特账号 RSS"""
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{account}/rss"
        xml_text = fetch_url(url, timeout=timeout)
        if not xml_text:
            continue
        results = parse_rss(xml_text)
        if results:
            # 只保留 AI 相关推文
            ai_kw = ["AI", "GPT", "LLM", "OpenAI", "model", "robot",
                     "智能", "模型", "开源", "推理", "训练", "算力",
                     "agent", "Agent", "NVIDIA", "英伟达", "Gemini",
                     "Claude", "Llama", "DeepSeek", "deepseek"]
            filtered = []
            for r in results:
                text = f"{r.get('title', '')} {r.get('body', '')}"
                if any(kw.lower() in text.lower() for kw in ai_kw):
                    r["title"] = f"🐦 @{account}: {r['title']}"
                    filtered.append(r)
            short_host = instance.split("//")[1][:18]
            print(f"     @{account} via {short_host}: {len(results)}条 → {len(filtered)}条AI")
            return filtered
    return []


def fetch_ai_twitter() -> list[dict]:
    """抓取推特 AI 圈最新推文"""
    all_tweets = []
    seen = set()
    for account in TWITTER_AI_ACCOUNTS:
        tweets = fetch_nitter_rss(account)
        for t in tweets:
            key = t["title"][:30]
            if key not in seen:
                seen.add(key)
                all_tweets.append(t)
        time.sleep(0.5)
    print(f"  🐦 推特AI圈 总计 {len(all_tweets)} 条")
    return all_tweets


def search_news(config: dict, min_count: int = 15) -> list[dict]:
    """多来源搜索"""
    seen_urls = set()
    seen_titles = set()
    all_results = []

    def add(r):
        url_key = r["href"].split("?")[0].rstrip("/")
        title_key = r["title"][:15]
        if url_key in seen_urls or title_key in seen_titles:
            return
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        all_results.append(r)

    # ── 1. Google News RSS ──
    print("  🔍 Google News RSS 搜索...")
    for q in config["google_queries"]:
        encoded = urllib.parse.quote(q)
        url = f"{GOOGLE_NEWS_BASE}?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        xml_text = fetch_url(url)
        if xml_text:
            for r in parse_google_news_rss(xml_text):
                add(r)
        time.sleep(0.8)
    print(f"    已获取 {len(all_results)} 条")

    # ── 2. 中文 RSS 源 ──
    for feed_url in config.get("rss_feeds", []):
        if len(all_results) >= min_count:
            break
        print(f"  🔗 RSS: {feed_url[:55]}...")
        xml_text = fetch_url(feed_url)
        if xml_text:
            for r in parse_rss(xml_text):
                add(r)
        time.sleep(0.5)

    # ── 3. 推特 AI 圈（仅科技日报） ──
    if config.get("twitter"):
        tweets = fetch_ai_twitter()
        for t in tweets:
            add(t)

    print(f"  📥 总计获取 {len(all_results)} 条去重结果")
    return all_results


def select_best(results: list[dict], count: int = 10) -> list[dict]:
    """精选最有价值的新闻"""
    if len(results) <= count:
        return results

    high = ["发布", "合作", "融资", "收购", "新规", "突破", "上市",
            "推出", "AI", "大模型", "芯片", "业绩", "增长"]
    medium = ["趋势", "报告", "数据", "政策", "动态", "创新"]

    def score(r):
        s = 0
        text = r["title"] + r.get("body", "")
        if 8 <= len(r["title"]) <= 50:
            s += 1
        for kw in high:
            if kw in text:
                s += 2
                break
        for kw in medium:
            if kw in text:
                s += 1
                break
        for kw in ["2026", "6月", "最新", "刚刚"]:
            if kw in r["title"]:
                s += 1
        return s

    scored = [(score(r), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:count]]


def build_post(topic: str, items: list[dict]) -> dict:
    """构建飞书富文本 post 消息（标题可点击 + 摘要文字）"""
    config = TOPIC_CONFIG[topic]
    today = datetime.now().strftime("%Y.%m.%d")
    title = f"{config['title_prefix']} | {today}"

    content_blocks = []
    sections = config["sections"]
    per_section = max(1, min(4, len(items) // len(sections)))

    idx = 0
    for section_title, _ in sections:
        section_items = []
        for _ in range(per_section):
            if idx >= len(items):
                break
            section_items.append(items[idx])
            idx += 1

        if not section_items:
            continue

        # 区块标题
        content_blocks.append([{"tag": "text", "text": section_title}])

        for item in section_items:
            # 标题（可点击链接）
            short_title = item["title"]
            content_blocks.append([
                {"tag": "a", "text": f"▶ {short_title}", "href": item["href"]}
            ])
            # 摘要文字
            summary = item.get("body", "").strip()
            # 再次确保无残留 HTML
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            # 截断过长摘要
            if len(summary) > 60:
                summary = summary[:58] + "…"
            if summary and summary != item["title"]:
                content_blocks.append([{"tag": "text", "text": f"{summary}"}])
            content_blocks.append([{"tag": "text", "text": ""}])

    # 剩余条目
    while idx < len(items):
        item = items[idx]
        short_title = item["title"] if len(item["title"]) <= 30 else item["title"][:28] + "…"
        content_blocks.append([
            {"tag": "a", "text": f"▶ {short_title}", "href": item["href"]}
        ])
        summary = re.sub(r"<[^>]+>", (item.get("body") or "").strip()).strip()
        if len(summary) > 60:
            summary = summary[:58] + "…"
        if summary and summary != item["title"]:
            content_blocks.append([{"tag": "text", "text": f"{summary}"}])
        content_blocks.append([{"tag": "text", "text": ""}])
        idx += 1

    # 底部分割线 + footer
    content_blocks.append([{"tag": "text", "text": "——"}])
    content_blocks.append([{"tag": "text", "text": config["footer"]}])

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content_blocks,
                }
            }
        },
    }


def push_to_feishu(payload: dict) -> bool:
    """推送飞书"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            ok = result.get("StatusCode") == 0 or result.get("code") == 0
            if ok:
                print("✅ 推送成功")
            else:
                print(f"❌ 推送失败: {result}", file=sys.stderr)
            return ok
    except Exception as e:
        print(f"❌ 推送异常: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, choices=["beauty", "tech"])
    args = parser.parse_args()

    config = TOPIC_CONFIG[args.topic]
    print(f"🔍 开始生成 {config['title_prefix']}...")

    results = search_news(config, min_count=15)
    print(f"📥 共获取 {len(results)} 条结果")

    if not results:
        print("❌ 无搜索结果，退出", file=sys.stderr)
        sys.exit(1)

    selected = select_best(results, count=10)
    print(f"⭐ 精选 {len(selected)} 条")

    payload = build_post(args.topic, selected)
    ok = push_to_feishu(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
