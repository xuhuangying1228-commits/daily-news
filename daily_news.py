#!/usr/bin/env python3
"""美妆/科技行业日报 — GitHub Actions 定时推送飞书
数据来源：Google News RSS（中文区）+ 精选RSS源
"""

import os
import sys
import json
import time
import argparse
import urllib.request
from datetime import datetime
from xml.etree import ElementTree as ET


# ──────────────── 飞书 Webhook ────────────────
FEISHU_URL = os.environ["FEISHU_WEBHOOK_URL"]

# ──────────────── 通用请求头 ────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ──────────────── Google News RSS 搜索 ────────────────
# hl=zh-CN&gl=CN 确保返回中文内容
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"

GOOGLE_BEAUTY_QUERIES = [
    "美妆 化妆品 最新",
    "护肤 品牌 最新动态",
    "国货美妆 趋势",
    "化妆品行业 市场",
    "美容 护肤品 新规",
]

GOOGLE_TECH_QUERIES = [
    "AI 人工智能 最新",
    "大模型 LLM 发布",
    "手机 新品 发布 2026",
    "芯片 半导体 最新",
    "科技行业 动态 2026",
    "华为 苹果 小米 最新",
]

# ──────────────── 中文 RSS 源（作为补充） ────────────────
CHINESE_RSS_FEEDS = {
    "tech": [
        "https://www.ithome.com/rss/",
        "https://36kr.com/feed",
    ],
    "beauty": [
        # 美妆类可用RSS较少，主要靠Google News
    ],
}

# ──────────────── 主题配置 ────────────────
TOPIC_CONFIG = {
    "beauty": {
        "title_prefix": "\U0001f484 美妆行业日报",
        "sections": [
            ("\U0001f4ca 市场动态", "数据、业绩、规模"),
            ("\U0001f3ed 行业事件", "品牌动态、合作、展会"),
            ("\U0001f50d 趋势洞察", "产品趋势、消费洞察、政策"),
        ],
        "google_queries": GOOGLE_BEAUTY_QUERIES,
        "rss_feeds": CHINESE_RSS_FEEDS["beauty"],
        "footer": "\U0001f4a1 数据来源：12个公众号 + Google News中文区 | 每日9:00自动推送",
    },
    "tech": {
        "title_prefix": "\U0001f916 AI\u00b73C\u00b7科技日报",
        "sections": [
            ("\U0001f4ca 行业动态", "市场数据、行业趋势、投融资"),
            ("\U0001f3ed 公司事件", "产品发布、企业动态、合作并购"),
            ("\U0001f50d 技术趋势", "AI突破、芯片进展、前沿技术"),
        ],
        "google_queries": GOOGLE_TECH_QUERIES,
        "rss_feeds": CHINESE_RSS_FEEDS["tech"],
        "footer": "\U0001f4a1 来源：Google News中文区 + IT之家/36氪 | 精选10条 \u00b7 每日9:00自动推送",
    },
}


def fetch_url(url: str, timeout: int = 15) -> str | None:
    """获取URL内容"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  \u26a0 请求失败 [{url[:60]}]: {e}", file=sys.stderr)
        return None


def parse_google_news_rss(xml_text: str) -> list[dict]:
    """解析 Google News RSS，提取标题、链接、摘要"""
    results = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = None
            link = None
            description = None
            for child in item:
                tag = child.tag.lower()
                # 处理命名空间
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                if tag == "title":
                    title = (child.text or "").strip()
                    # Google News 标题末尾有 " - 来源名"
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0]
                elif tag == "link":
                    link = (child.text or "").strip()
                elif tag == "description":
                    description = (child.text or "").strip()

            if title and link:
                results.append({
                    "title": title,
                    "href": link,
                    "body": description or title,
                })
    except ET.ParseError as e:
        print(f"  \u26a0 RSS解析失败: {e}", file=sys.stderr)
    return results


def parse_rss(xml_text: str) -> list[dict]:
    """解析标准 RSS 2.0"""
    results = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
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
                    link = (child.text or "").strip()
                elif tag in ("description", "summary", "content"):
                    txt = (child.text or "").strip()
                    if txt and len(txt) > len(desc or ""):
                        desc = txt

            if title and link and "http" in link:
                # 去除HTML标签
                clean_desc = desc or title
                # 简单去HTML
                import re
                clean_desc = re.sub(r"<[^>]+>", "", clean_desc).strip()
                results.append({
                    "title": title,
                    "href": link,
                    "body": clean_desc[:120],
                })
    except ET.ParseError as e:
        print(f"  \u26a0 RSS解析失败: {e}", file=sys.stderr)
    return results


def search_news(config: dict, min_count: int = 15) -> list[dict]:
    """多来源搜索：Google News RSS + 中文RSS源"""
    seen_urls = set()
    seen_titles = set()
    all_results = []

    # ── 1. Google News RSS 搜索 ──
    print("  \U0001f50d Google News RSS 搜索...")
    for q in config["google_queries"]:
        encoded = urllib.parse.quote(q)
        url = f"{GOOGLE_NEWS_BASE}?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        xml_text = fetch_url(url)
        if not xml_text:
            continue
        results = parse_google_news_rss(xml_text)
        for r in results:
            url_key = r["href"].split("?")[0].rstrip("/")
            title_key = r["title"][:15]
            if url_key in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            all_results.append(r)
        time.sleep(1)

    print(f"    已获取 {len(all_results)} 条")

    # ── 2. 中文 RSS 源补充 ──
    for feed_url in config["rss_feeds"]:
        if len(all_results) >= min_count:
            break
        print(f"  \U0001f517 RSS: {feed_url[:50]}...")
        xml_text = fetch_url(feed_url)
        if not xml_text:
            continue
        results = parse_rss(xml_text)
        for r in results:
            url_key = r["href"].split("?")[0].rstrip("/")
            title_key = r["title"][:15]
            if url_key in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            all_results.append(r)
        time.sleep(1)

    print(f"  \U0001f4e5 总计获取 {len(all_results)} 条去重结果")
    return all_results


def select_best(results: list[dict], count: int = 10) -> list[dict]:
    """从结果中精选最有价值的新闻"""
    if len(results) <= count:
        return results

    # 关键词打分
    high_value = ["发布", "合作", "融资", "收购", "新规", "突破", "上市",
                  "发布", "推出", "AI", "大模型", "芯片", "业绩", "增长"]
    medium_value = ["趋势", "报告", "数据", "政策", "动态", "创新"]

    def score(r):
        s = 0
        title = r["title"]
        body = r.get("body", "")
        text = title + body
        # 标题长度合理
        if 8 <= len(title) <= 50:
            s += 1
        # 高价值关键词
        for kw in high_value:
            if kw in text:
                s += 2
                break
        for kw in medium_value:
            if kw in text:
                s += 1
                break
        # 有时间感的标题更好
        for kw in ["2026", "6月", "最新", "刚刚"]:
            if kw in title:
                s += 1
        return s

    scored = [(score(r), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:count]]


def build_post(topic: str, items: list[dict]) -> dict:
    """构建飞书 post 消息体"""
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

        content_blocks.append([{"tag": "text", "text": section_title}])
        for item in section_items:
            short_title = item["title"]
            if len(short_title) > 24:
                short_title = short_title[:22] + "\u2026"
            content_blocks.append([
                {"tag": "a", "text": f"\u25b6 {short_title}", "href": item["href"]}
            ])
            summary = item.get("body", "").strip()
            if len(summary) > 50:
                summary = summary[:48] + "\u2026"
            if summary:
                content_blocks.append([
                    {"tag": "text", "text": f"   {summary}"}
                ])
            content_blocks.append([{"tag": "text", "text": ""}])

    # 剩余项目追加
    while idx < len(items):
        item = items[idx]
        short_title = item["title"][:22] + "\u2026" if len(item["title"]) > 24 else item["title"]
        content_blocks.append([
            {"tag": "a", "text": f"\u25b6 {short_title}", "href": item["href"]}
        ])
        content_blocks.append([{"tag": "text", "text": ""}])
        idx += 1

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
    """推送飞书消息"""
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
                print(f"\u2705 推送成功")
            else:
                print(f"\u274c 推送失败: {result}", file=sys.stderr)
            return ok
    except Exception as e:
        print(f"\u274c 推送异常: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, choices=["beauty", "tech"])
    args = parser.parse_args()

    config = TOPIC_CONFIG[args.topic]
    print(f"\U0001f50d 开始生成 {config['title_prefix']}...")

    results = search_news(config, min_count=15)
    print(f"\U0001f4e5 共获取 {len(results)} 条结果")

    if not results:
        print("\u274c 无搜索结果，退出", file=sys.stderr)
        sys.exit(1)

    selected = select_best(results, count=10)
    print(f"\u2b50 精选 {len(selected)} 条")

    payload = build_post(args.topic, selected)
    ok = push_to_feishu(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
