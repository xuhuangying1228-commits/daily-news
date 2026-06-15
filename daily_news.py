#!/usr/bin/env python3
"""美妆/科技行业日报 — GitHub Actions 定时推送飞书"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from duckduckgo_search import DDGS

# ──────────────── 飞书 Webhook ────────────────
FEISHU_URL = os.environ["FEISHU_WEBHOOK_URL"]

# ──────────────── 搜索配置 ────────────────
BEAUTY_QUERIES = [
    "聚美丽 美妆 最新 2026",
    "青眼 美妆 最新 2026",
    "化妆品观察 品观 最新 2026",
    "化妆品财经在线 CBO 最新 2026",
    "LADYMAX 美妆 最新 2026",
    "美妆内行人 最新 2026",
    "华妆志 美妆 最新",
    "化妆品报 美妆 最新 2026",
    "KEV美妆圈 最新",
    "C2CC新传媒 美妆 最新",
    "美博会 美妆 最新 2026",
    "everybody关注 美妆",
    "美妆护肤 行业 市场动态 2026",
    "化妆品 国货品牌 最新动态 2026",
    "美妆行业 政策法规 2026",
]

TECH_QUERIES = [
    "AI 人工智能 最新动态 2026",
    "大模型 LLM 最新发布 2026",
    "AI应用 落地 最新 2026",
    "手机 最新发布 2026",
    "智能硬件 可穿戴 最新 2026",
    "笔记本电脑 数码产品 最新 2026",
    "科技行业 最新动态 2026",
    "华为 小米 苹果 最新 2026",
    "芯片 半导体 最新 2026",
    "科技巨头 最新动态 2026",
    "互联网 科技公司 最新 2026",
    "科技政策 监管 最新 2026",
]

TOPIC_CONFIG = {
    "beauty": {
        "title_prefix": "💄 美妆行业日报",
        "sections": [
            ("📊 市场动态", "数据、业绩、规模"),
            ("🏭 行业事件", "品牌动态、合作、展会"),
            ("🔬 趋势洞察", "产品趋势、消费洞察、政策"),
        ],
        "queries": BEAUTY_QUERIES,
        "footer": "💡 数据来源：12个公众号 + 公开报道 | 每日9:00自动推送",
    },
    "tech": {
        "title_prefix": "🤖 AI·3C·科技日报",
        "sections": [
            ("📊 行业动态", "市场数据、行业趋势、投融资"),
            ("🏭 公司事件", "产品发布、企业动态、合作并购"),
            ("🔬 技术趋势", "AI突破、芯片进展、前沿技术"),
        ],
        "queries": TECH_QUERIES,
        "footer": "💡 来源：公开报道 | 精选10条 · 每日9:00自动推送",
    },
}


def search_news(queries: list[str], max_per_query: int = 3) -> list[dict]:
    """多来源搜索，返回去重后的结果列表"""
    seen_urls = set()
    seen_titles = set()
    all_results = []

    for q in queries:
        try:
            results = list(DDGS().text(q, max_results=max_per_query))
        except Exception as e:
            print(f"  ⚠ 搜索失败 [{q[:20]}...]: {e}", file=sys.stderr)
            continue

        for r in results:
            title = (r.get("title") or "").strip()
            href = (r.get("href") or "").strip()
            body = (r.get("body") or "").strip()

            url_key = href.split("?")[0].rstrip("/")
            title_key = title[:20]

            if url_key in seen_urls or title_key in seen_titles:
                continue
            if not title or not href:
                continue
            # 过滤低质量来源
            skip_domains = ["facebook.com", "instagram.com", "youtube.com", "tiktok.com"]
            if any(d in href for d in skip_domains):
                continue

            seen_urls.add(url_key)
            seen_titles.add(title_key)
            all_results.append({"title": title, "href": href, "body": body})

        time.sleep(1.5)  # 避免请求过密

    return all_results


def select_best(results: list[dict], count: int = 10) -> list[dict]:
    """从结果中精选最有价值的新闻"""
    if len(results) <= count:
        return results

    # 按标题长度和内容质量打分
    def score(r):
        s = 0
        title = r["title"]
        body = r["body"]
        if len(title) >= 8 and len(title) <= 40:
            s += 1
        if len(body) >= 20:
            s += 1
        if any(kw in title + body for kw in ["发布", "合作", "融资", "收购", "新规", "突破", "上市"]):
            s += 1
        if any(kw in title for kw in ["2026", "6月", "最新"]):
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

    # 按板块分配
    per_section = max(3, len(items) // len(config["sections"]) + 1)
    idx = 0
    for section_title, _ in config["sections"]:
        content_blocks.append([{"tag": "text", "text": section_title}])
        for i in range(per_section):
            if idx >= len(items):
                break
            item = items[idx]
            # 截断过长的标题
            short_title = item["title"]
            if len(short_title) > 22:
                short_title = short_title[:20] + "…"
            content_blocks.append([
                {"tag": "a", "text": f"▶ {short_title}", "href": item["href"]}
            ])
            summary = item["body"]
            if len(summary) > 40:
                summary = summary[:38] + "…"
            content_blocks.append([
                {"tag": "text", "text": f"   {summary}"}
            ])
            content_blocks.append([{"tag": "text", "text": ""}])
            idx += 1

    # 如果还有多余项目，追加到最后
    while idx < len(items):
        item = items[idx]
        short_title = item["title"][:20] + "…" if len(item["title"]) > 22 else item["title"]
        content_blocks.append([
            {"tag": "a", "text": f"▶ {short_title}", "href": item["href"]}
        ])
        summary = item["body"][:38] + "…" if len(item["body"]) > 40 else item["body"]
        content_blocks.append([{"tag": "text", "text": f"   {summary}"}])
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
    import urllib.request

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
                print(f"✅ 推送成功")
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
    print(f"🔍 开始搜索 {config['title_prefix']}...")

    results = search_news(config["queries"], max_per_query=3)
    print(f"📥 获取 {len(results)} 条去重结果")

    selected = select_best(results, count=10)
    print(f"⭐ 精选 {len(selected)} 条")

    # 如果不够10条，尝试补充搜索
    if len(selected) < 10:
        print(f"⚠ 当前 {len(selected)} 条，尝试补充搜索...")
        extra_queries = [f"{config['title_prefix']} 最新" for _ in range(3)]
        extra = search_news(extra_queries, max_per_query=3)
        existing_titles = {s["title"][:20] for s in selected}
        for r in extra:
            if r["title"][:20] not in existing_titles:
                selected.append(r)
                existing_titles.add(r["title"][:20])
                if len(selected) >= 10:
                    break
        print(f"⭐ 补充后共 {len(selected)} 条")

    payload = build_post(args.topic, selected)
    ok = push_to_feishu(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
