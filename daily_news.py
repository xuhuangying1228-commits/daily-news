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
from html import unescape
from xml.etree import ElementTree as ET


# ──────────────── 飞书 Webhook ────────────────
FEISHU_URL = os.environ["FEISHU_WEBHOOK_URL"]

# ──────────────── 通用请求头 ────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_html(text: str) -> str:
    """去除 HTML 标签 + 转义 HTML 实体（&nbsp; &amp; 等）"""
    text = re.sub(r"<[^>]+>", "", text)      # 去掉标签
    text = unescape(text)                     # &nbsp; → 空格, &amp; → & 等
    return text.strip()


def extract_summary(title: str, raw_desc: str) -> str:
    """从 RSS description 提取真正文章摘要。
    返回空字符串 = 无有效摘要，不显示。
    """
    if not raw_desc:
        return ""

    text = clean_html(raw_desc)

    # ── 基础去重 ──
    if not text or text == title:
        return ""

    # ── 仅有一个链接（无实际正文）→ 放弃 ──
    if text.startswith("http") and len(text) < 100:
        return ""

    # ── 剥掉前面的来源名（英文短词 + 双空格/制表符）──
    # Google News 格式："CNN  &nbsp;&nbsp;  title ..."
    text = re.sub(r"^[A-Za-z0-9.·\s]{2,30}\s{2,}", "", text).strip()
    # 中文来源名 "新华网  "、"36氪  " 等（1-6个中文字 + 空格）
    text = re.sub(r"^[\u4e00-\u9fff]{1,6}\s{2,}", "", text).strip()

    # ── 剥掉剩余开头中的已知来源尾缀（`source<br clear=...>` → 只剩 `source`）──
    # 这些是 Google News 描述里残留的纯来源名，没有正文
    SOURCE_TRASH = re.compile(
        r"^(?:"
        r"AgeClub|新华网|新浪财经|雪球|界面新闻|澎湃新闻|36氪|虎嗅|钛媒体|"
        r"第一财经|每日经济新闻|财联社|华尔街见闻|蓝鲸|创业邦|"
        r"品玩|极客公园|机器之心|量子位|InfoQ|CSDN|开源中国|"
        r"Reuters|Bloomberg|CNN|BBC|NYT|WSJ|FT|Forbes|"
        r"TechCrunch|The[ ]Verge|Wired|Ars[ ]Technica|"
        r"VentureBeat|ZDNet|CNBC|Business[ ]Insider|"
        r"Engadget|Gizmodo|Mashable|The[ ]Information|"
        r"Tom.?.Hardware|AnandTech|MacRumors|9to5Mac|"
        r"SamMobile|Android[ ]Authority|Phone[ ]Arena|"
        r"GSMArena|Neowin|Windows[ ]Central|The[ ]Register|"
        r"GitHub|Hacker[ ]News|Reddit|Twitter|X\.com|"
        r"IBM|Microsoft|Google|Apple|Meta|Amazon|OpenAI|NVIDIA|"
        r"CBNData|美业观察|化妆品观察|青眼|聚美丽|品观|"
        r"华丽志|WWD|Beauty[ ]Matter|Cosmetic[ ]Business|"
        r"Global[ ]Cosmetics[ ]News|Premium[ ]Beauty[ ]News"
        r")$"
    )
    if SOURCE_TRASH.match(text):
        return ""

    # ── 剥掉标题前缀 ──
    text = _strip_title(text, title)

    if not text or text == title:
        return ""

    # ── 最终校验：必须是"看起来像文章摘要"的文本 ──
    text = text.strip()
    # 去掉末尾残余的来源名（"xx 雪球"、"xx IBM" 等）
    text = re.sub(r"\s+(?:雪球|新浪|网易|腾讯|搜狐|凤凰|新华网|界面|澎湃|"
                  r"36氪|钛媒体|财联社|华尔街见闻|蓝鲸|"
                  r"Reuters|Bloomberg|CNN|BBC|TechCrunch|The[ ]Verge|"
                  r"Wired|Forbes|CNBC|IBM|Microsoft|Google|Apple|Meta)$",
                  "", text).strip()
    # 太短 → 不是摘要
    if len(text) < 12:
        return ""
    # 纯来源名（中文 <= 6 字，英文 <= 20 字符）→ 不是摘要
    if re.match(r"^[\u4e00-\u9fff]{1,6}$", text):
        return ""
    if re.match(r"^[A-Za-z0-9.·&\s]{1,20}$", text):
        return ""
    # 以查看更多/阅读全文结尾但无实质内容
    if re.match(r"^.{0,5}(查看更多|阅读全文|Read more)\.*$", text):
        return ""

    return text


def _strip_title(text: str, title: str) -> str:
    """剥掉文本开头的标题（含模糊匹配）"""
    if text.startswith(title):
        return text[len(title):].lstrip(" -–:：,，|·….")

    # 模糊：标题前一半（至少 8 字符）出现在文本开头
    for cut in range(len(title), 7, -1):
        prefix = title[:cut]
        if text.startswith(prefix):
            remainder = text[len(prefix):].lstrip(" -–:：,，|·….")
            if len(remainder) >= 5:
                return remainder
            return ""  # 只有前缀无实质内容
    return text

# ──────────────── Google News RSS ────────────────
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"

GOOGLE_BEAUTY_QUERIES = [
    # ── 国际大牌 ──
    "欧莱雅 雅诗兰黛 资生堂 最新动态 2026",
    "LVMH 美妆 品牌 Dior 娇兰 纪梵希 最新",
    "宝洁 联合利华 美容 护肤 品牌 动态",
    "Coty 拜尔斯道夫 妮维雅 La Prairie 最新",
    # ── 国货品牌 ──
    "珀莱雅 薇诺娜 华熙生物 新品 业绩",
    "完美日记 花西子 毛戈平 最新动态 2026",
    "韩束 丸美 自然堂 谷雨 溪木源 品牌",
    "巨子生物 可复美 瑷尔博士 最新",
    # ── 韩妆日妆 ──
    "爱茉莉太平洋 雪花秀 LG生活健康 最新",
    "高丝 花王 芳珂 Fancl 美妆 品牌",
    # ── 行业综合 ──
    "美妆 品牌 融资 收购 上市 2026",
    "化妆品 护肤 新品 发布 成分",
    "化妆品行业 市场 趋势 新规 2026",
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
            ("🏷️ 品牌动态", "新品发布、业绩财报、品牌合作"),
            ("🤝 投融资·并购", "融资、收购、上市"),
            ("📊 行业事件", "市场趋势、政策新规、渠道变化"),
            ("🔍 产品·成分", "新品技术、热门成分、研发动态"),
        ],
        "google_queries": GOOGLE_BEAUTY_QUERIES,
        "rss_feeds": CHINESE_RSS_FEEDS["beauty"],
        "twitter": False,
        "footer": "💡 来源：Google News品牌搜索（13个搜索词覆盖国际大牌+国货+韩妆日妆） | 精选14条 · 每日9:00自动推送",
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
                body = extract_summary(title, description or "")
                results.append({
                    "title": title,
                    "href": link,
                    "body": body,
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
                body = extract_summary(title, desc or "")
                results.append({
                    "title": title,
                    "href": link,
                    "body": body[:120],
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
            # 摘要文字（extract_summary 已保证 ≠ 标题）
            body = (item.get("body") or "").strip()
            if len(body) > 80:
                body = body[:78] + "…"
            if body:
                content_blocks.append([{"tag": "text", "text": body}])
            content_blocks.append([{"tag": "text", "text": ""}])

    # 剩余条目
    while idx < len(items):
        item = items[idx]
        short_title = item["title"] if len(item["title"]) <= 30 else item["title"][:28] + "…"
        content_blocks.append([
            {"tag": "a", "text": f"▶ {short_title}", "href": item["href"]}
        ])
        body = (item.get("body") or "").strip()
        if len(body) > 80:
            body = body[:78] + "…"
        if body:
            content_blocks.append([{"tag": "text", "text": body}])
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

    selected = select_best(results, count=14)
    print(f"⭐ 精选 {len(selected)} 条")

    payload = build_post(args.topic, selected)
    ok = push_to_feishu(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
