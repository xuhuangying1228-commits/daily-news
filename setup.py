#!/usr/bin/env python3
"""
🧙 行业日报 · 一键配置向导

帮你把飞书 Webhook 配置到 GitHub Actions Secret，
只需输入机器人地址和 GitHub Token，其他全自动。

用法：
    python3 setup.py

依赖：Python 3.9+（系统自带即可），PyNaCl（自动检测）
"""

import os
import sys
import json
import re
import base64
import urllib.request
import subprocess


def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"


def detect_repo() -> str | None:
    """尝试从 git remote 自动检测 GitHub 仓库"""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        # 支持 git@github.com:user/repo.git 和 https://github.com/user/repo
        m = re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$", out)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


def get_public_key(token: str, repo: str) -> tuple[str, str]:
    """获取仓库的 Actions Secrets 公钥"""
    url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
        return data["key_id"], data["key"]


def encrypt_secret(value: str, public_key_b64: str) -> str:
    """用仓库公钥加密 Secret 值"""
    from nacl import encoding, public
    pk = public.PublicKey(public_key_b64, encoding.Base64Encoder())
    sealed = public.SealedBox(pk)
    return base64.b64encode(sealed.encrypt(value.encode())).decode()


def set_secret(token: str, repo: str, name: str, encrypted: str, key_id: str) -> bool:
    """设置 GitHub Actions Secret"""
    url = f"https://api.github.com/repos/{repo}/actions/secrets/{name}"
    payload = json.dumps({
        "encrypted_value": encrypted,
        "key_id": key_id,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    req.get_method = lambda: "PUT"
    try:
        with urllib.request.urlopen(req) as r:
            return r.status in (201, 204)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(red(f"\n  ❌ HTTP {e.code}: {body[:200]}"))
        return False


def main():
    print()
    print(bold("🧙 行业日报 · 一键配置向导"))
    print("─" * 50)
    print()

    # ── Step 1: 仓库 ──
    detected = detect_repo()
    if detected:
        print(f"  📁 检测到仓库: {green(detected)}")
        print(f"     确认即回车，修改直接输入 →")
        repo = input("  > ").strip()
        if not repo:
            repo = detected
    else:
        print("  📁 请输入你的 GitHub 仓库名（格式: 用户名/仓库名）")
        print("     例如: xiaoming/daily-news")
        repo = input("  > ").strip()

    if not repo or "/" not in repo:
        print(red("  ❌ 仓库名格式不对，需要 用户名/仓库名"))
        sys.exit(1)

    # ── Step 2: Webhook URL ──
    print()
    print("  🔗 请输入飞书机器人 Webhook URL")
    print("     （在飞书群 → 设置 → 群机器人 → 添加 → 复制地址）")
    webhook = input("  > ").strip()

    if not webhook or "open.feishu.cn" not in webhook:
        print(yellow("  ⚠  地址看起来不太对，确认一下？"))
        confirm = input("  按 y 继续 / n 退出 [y]: ").strip().lower()
        if confirm == "n":
            print("  已取消")
            sys.exit(0)

    # ── Step 3: GitHub Token ──
    print()
    print("  🔑 请输入 GitHub Personal Access Token")
    print("     需要权限：repo（仓库完全访问）")
    print("     创建地址：https://github.com/settings/tokens/new")
    print("     Token 不会保存到本地，仅用于本次配置")
    token = input("  > ").strip()

    if not token or not token.startswith(("ghp_", "github_pat_")):
        print(yellow("  ⚠  Token 格式可能不对（通常以 ghp_ 或 github_pat_ 开头）"))
        confirm = input("  按 y 继续 / n 退出 [y]: ").strip().lower()
        if confirm == "n":
            print("  已取消")
            sys.exit(0)

    # ── Step 4: 配置 Secret ──
    print()
    print(f"  🔐 正在配置 {repo} ...")

    try:
        key_id, public_key = get_public_key(token, repo)
    except Exception as e:
        print(red(f"  ❌ 获取仓库公钥失败: {e}"))
        print(yellow("  💡 可能原因：Token 权限不够、仓库名不对、网络问题"))
        sys.exit(1)

    try:
        encrypted = encrypt_secret(webhook, public_key)
    except ImportError:
        print(red("  ❌ 缺少 PyNaCl 库"))
        print("     请运行: pip3 install pynacl")
        sys.exit(1)

    if set_secret(token, repo, "FEISHU_WEBHOOK_URL", encrypted, key_id):
        print(green("  ✅ FEISHU_WEBHOOK_URL 配置成功！"))
    else:
        print(red("  ❌ 配置失败，请检查 Token 权限（需要 repo 完全访问）"))
        sys.exit(1)

    # ── Step 5: 验证 ──
    print()
    print(bold("✅ 全部完成！"))
    print()
    print("  📋 下一步：")
    print(f"     1. 打开仓库 Actions 页面确认已启用：")
    print(f"        https://github.com/{repo}/actions")
    print("     2. 明天上午 9:00 会自动推送第一条日报")
    print("     3. 想改行业？编辑 topics.yaml 即可")
    print()
    print("  🎉 祝日报顺利！")


if __name__ == "__main__":
    main()
