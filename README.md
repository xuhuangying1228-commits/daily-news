# 每日行业日报 · GitHub Actions 版

每天 9:00（北京时间）自动推送美妆和科技行业日报到飞书。

## 工作原理

```
GitHub Actions (云端) → 搜索网络资讯 → 精选10条 → 飞书 Webhook → 你的飞书
```

不需要电脑开机，不需要安装任何东西。

## 设置步骤

### 1. 创建 GitHub 仓库

在 GitHub 新建一个仓库，命名为 `daily-news`（或任意名称）。

### 2. 设置飞书 Webhook Secret

- 进入仓库 **Settings → Secrets and variables → Actions**
- 点击 **New repository secret**
- Name: `FEISHU_WEBHOOK_URL`
- Value: `https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook地址`

### 3. 推送代码

```bash
cd daily-news-actions
git init
git add .
git commit -m "初始提交"
git remote add origin https://github.com/你的用户名/daily-news.git
git push -u origin main
```

### 4. 手动测试

进入 GitHub 仓库的 **Actions** 标签 → 选择 "美妆行业日报" → **Run workflow**

## 文件结构

```
.
├── .github/workflows/
│   ├── beauty-news.yml    # 美妆日报（每天 9:00）
│   └── tech-news.yml      # 科技日报（每天 9:00）
├── daily_news.py          # 搜索+推送脚本
├── requirements.txt
└── README.md
```
