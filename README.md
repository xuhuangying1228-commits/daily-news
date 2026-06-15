# 📰 行业日报 · 飞书自动推送

每天早上 9:00 自动抓取行业新闻，分类整理后推到飞书群。

当前支持：**美妆** · **AI科技**  
加新行业？改 `topics.yaml` 就行。

---

## 🚀 3 步上手（伙伴版）

### 第 1 步：Fork 这个仓库

点右上角 **Fork** → 选择你自己的账号 → 完成。

### 第 2 步：配置飞书机器人

先在你的飞书群里添加一个**自定义机器人**：
- 群设置 → 群机器人 → 添加机器人 → 自定义机器人
- 复制 Webhook 地址（格式：`https://open.feishu.cn/...`）

然后回来，在终端运行：

```bash
python3 setup.py
```

按提示输入 Webhook 地址和 GitHub Token 即可。Token 需要 `repo` 权限，[点这里创建](https://github.com/settings/tokens/new)。

> 不想用脚本？手动配置也行：仓库 → Settings → Secrets and variables → Actions → New repository secret
> - Name: `FEISHU_WEBHOOK_URL`
> - Secret: 你的飞书 Webhook 地址

### 第 3 步：启用 Actions

打开 `https://github.com/你的用户名/daily-news/actions`，点击绿色的 **"I understand my workflows, go ahead and enable them"**。

**完成！** 明天早上 9 点就能在群里收到日报了 🎉

---

## ✏️ 加新行业？改 YAML 就行

编辑 `topics.yaml`，在 `topics:` 下面加一段配置。比如想加"食品行业"：

```yaml
topics:
  # ... 上面是已有的 beauty / tech ...

  food:
    enabled: true
    title_prefix: "🍔 食品行业日报"
    sections:
      - ["🏷️ 品牌动态", "新品发布、财报、合作"]
      - ["📊 行业事件", "政策、趋势、数据"]
    google_queries:
      - "食品行业 新品 融资 2026"
      - "零食 饮料 品牌 最新动态"
    rss_feeds: []
    twitter: false
    footer: "💡 来源：Google News | 每日9:00推送"
    news_count: 10
```

保存 → 推送 → 明天就生效。不用改代码。

---

## 🔧 关闭某个行业

把 `topics.yaml` 里对应行业的 `enabled: true` 改成 `enabled: false` 即可。

---

## 🧪 手动测试

```bash
pip install pyyaml
FEISHU_WEBHOOK_URL="你的webhook地址" python3 daily_news.py --topic beauty
```

---

## 📁 文件说明

| 文件 | 作用 |
|------|------|
| `daily_news.py` | 核心脚本：搜索 → 精选 → 分类 → 推送 |
| `topics.yaml` | 行业配置（想改行业改这里） |
| `setup.py` | 一键配置向导 |
| `.github/workflows/daily-news.yml` | 定时任务（每天9点跑） |

---

## ❓ 常见问题

**Q: 没收到消息？**  
A: 检查仓库 Actions 是否启用、`FEISHU_WEBHOOK_URL` 是否正确、机器人是否还在群里。

**Q: 能改推送时间吗？**  
A: 编辑 `.github/workflows/daily-news.yml`，改 `cron` 表达式。`0 1 * * *` = UTC 1:00 = 北京时间 9:00。[Cron 参考](https://crontab.guru/)

**Q: 消息格式不满意？**  
A: 编辑 `daily_news.py` 里的 `build_post()` 函数，飞书富文本格式可自定义。

**Q: 搜索结果不好？**  
A: 编辑 `topics.yaml` 里的 `google_queries` 列表，调整搜索关键词。
