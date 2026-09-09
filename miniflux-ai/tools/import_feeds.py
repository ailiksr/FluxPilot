#!/usr/bin/env python3
"""Batch import and intelligent re-categorization script for Miniflux feeds.

Re-categorizes feeds based on content nature into 6 clean, professional groups:
  1. 🤖 系统与AI内参
  2. ⚡ 数字科技与效率
  3. 🛠️ 极客折腾与建站
  4. 📦 实用资源与开源
  5. ☕ 社区闲聊与泛读
  6. 🎁 活动福利与特惠
"""
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/opt/rss-ai/miniflux-ai")

CATEGORIES_SCHEMA = [
    {
        "title": "🤖 系统与AI内参",
        "feeds": [
            {
                "title": "֎Minifluxᴬᴵ Digest for you",
                "feed_url": "http://miniflux-ai/rss/digest",
                "site_url": "http://miniflux-ai",
                "crawler": False,
            }
        ],
    },
    {
        "title": "⚡ 数字科技与效率",
        "feeds": [
            {
                "title": "蓝点网",
                "feed_url": "https://www.landian.news/feed",
                "site_url": "https://www.landian.news",
                "scraper_rules": ".content-post",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
            {
                "title": "少数派",
                "feed_url": "https://sspai.com/feed",
                "site_url": "https://sspai.com",
                "scraper_rules": ".article__main__content, .post__body__extend__item__title, .post__body__extend__item__content, .prime__story__body",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
            {
                "title": "小众软件",
                "feed_url": "https://www.appinn.com/feed/",
                "site_url": "https://www.appinn.com",
                "scraper_rules": ".post-single-content",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
        ],
    },
    {
        "title": "🛠️ 极客折腾与建站",
        "feeds": [
            {
                "title": "挖站否-挖掘建站的乐趣",
                "feed_url": "https://wzfou.com/feed/",
                "site_url": "https://wzfou.com/",
                "scraper_rules": "#ftwp-postcontent",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
            {
                "title": "主机百科",
                "feed_url": "https://zhujiwiki.com/feed/",
                "site_url": "https://zhujiwiki.com",
                "scraper_rules": ".article-content",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
            {
                "title": "爱玩实验室",
                "feed_url": "https://iwanlab.com/feed/",
                "site_url": "https://iwanlab.com",
                "crawler": True,
            },
        ],
    },
    {
        "title": "📦 实用资源与开源",
        "feeds": [
            {
                "title": "资源荟萃 - LINUX DO",
                "feed_url": "https://linux.do/c/resource/14.rss",
                "site_url": "https://linux.do/c/resource/14",
                "crawler": False,
            },
            {
                "title": "ahhhhfs",
                "feed_url": "https://www.ahhhhfs.com/feed/",
                "site_url": "https://www.ahhhhfs.com",
                "scraper_rules": "article.post-content",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
            {
                "title": "不死鸟 - 分享为王官网",
                "feed_url": "https://iui.su/feed/",
                "site_url": "https://iui.su/",
                "scraper_rules": ".entry-content, .post-content, .article-content, article, main",
                "crawler": True,
            },
            {
                "title": "如有乐享",
                "feed_url": "https://51.ruyo.net/feed",
                "site_url": "https://51.ruyo.net",
                "scraper_rules": ".post-content-content",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
        ],
    },
    {
        "title": "☕ 社区闲聊与泛读",
        "feeds": [
            {
                "title": "搞七捻三 - LINUX DO",
                "feed_url": "https://linux.do/c/gossip/11.rss",
                "site_url": "https://linux.do/c/gossip/11",
                "scraper_rules": ".entry-content, .post-content, .article-content, article, main",
                "crawler": True,
            },
            {
                "title": "博海拾贝",
                "feed_url": "https://www.bohaishibei.com/feed/",
                "site_url": "https://www.bohaishibei.com",
                "scraper_rules": ".entry-content",
                "rewrite_rules": "add_dynamic_image,use_noscript_figure_images",
                "crawler": True,
            },
        ],
    },
    {
        "title": "🎁 活动福利与特惠",
        "feeds": [
            {
                "title": "福利羊毛 - LINUX DO",
                "feed_url": "https://linux.do/c/welfare/36.rss",
                "site_url": "https://linux.do/c/welfare/36",
                "scraper_rules": ".entry-content, .post-content, .article-content, article, main",
                "user_agent": "Mozilla/5.0 (compatible; Miniflux RSS; +https://miniflux.app)",
                "crawler": True,
            },
            {
                "title": "福利吧",
                "feed_url": "https://fuliba.net/feed",
                "site_url": "https://fuliba2023.net",
                "scraper_rules": ".article-content",
                "crawler": False,
            },
        ],
    },
]


def run_import():
    from core.miniflux_client import get_miniflux_client

    client = get_miniflux_client()

    print("=== 1. 确保并同步分类 ===")
    existing_cats = {c["title"]: c["id"] for c in client.get_categories()}
    category_map = {}

    for cat_item in CATEGORIES_SCHEMA:
        cat_title = cat_item["title"]
        if cat_title not in existing_cats:
            try:
                new_cat = client.create_category(title=cat_title)
                cat_id = new_cat["id"]
                print(f"  [+] 新建分类: {cat_title} (ID={cat_id})")
            except Exception as e:
                # In case it exists or name conflict
                all_now = {c["title"]: c["id"] for c in client.get_categories()}
                cat_id = all_now.get(cat_title, 1)
                print(f"  [!] 复用分类: {cat_title} (ID={cat_id})")
        else:
            cat_id = existing_cats[cat_title]
            print(f"  [✓] 既有分类: {cat_title} (ID={cat_id})")
        category_map[cat_title] = cat_id

    print("\n=== 2. 导入与迁移订阅源 ===")
    existing_feeds = {f["feed_url"].rstrip("/"): f for f in client.get_feeds()}
    # Also index by exact feed_url
    for f in client.get_feeds():
        existing_feeds[f["feed_url"]] = f

    total_added = 0
    total_updated = 0
    failed_feeds = []

    for cat_item in CATEGORIES_SCHEMA:
        cat_title = cat_item["title"]
        cat_id = category_map[cat_title]
        print(f"\n📁 【{cat_title}】:")

        for f_info in cat_item["feeds"]:
            f_url = f_info["feed_url"]
            f_title = f_info["title"]
            clean_url = f_url.rstrip("/")

            kwargs = {}
            if "scraper_rules" in f_info:
                kwargs["scraper_rules"] = f_info["scraper_rules"]
            if "rewrite_rules" in f_info:
                kwargs["rewrite_rules"] = f_info["rewrite_rules"]
            if "crawler" in f_info:
                kwargs["crawler"] = f_info["crawler"]
            if "user_agent" in f_info:
                kwargs["user_agent"] = f_info["user_agent"]

            existing = existing_feeds.get(f_url) or existing_feeds.get(clean_url)
            if existing:
                fid = existing["id"]
                try:
                    client.update_feed(fid, category_id=cat_id, **kwargs)
                    print(f"  [⟳ 迁移] #{fid} {f_title} ➔ 分类归入 [{cat_title}]")
                    total_updated += 1
                except Exception as e:
                    print(f"  [!] 更新 #{fid} {f_title} 失败: {e}")
            else:
                try:
                    new_fid = client.create_feed(f_url, category_id=cat_id, **kwargs)
                    print(f"  [+ 订阅] #{new_fid} {f_title} 成功入驻 [{cat_title}]")
                    total_added += 1
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  [✖ 失败] {f_title} ({f_url}): {e}")
                    failed_feeds.append({"title": f_title, "url": f_url, "error": str(e)})

    print("\n=== 3. 统计结果 ===")
    print(f"新建订阅源: {total_added} 个")
    print(f"迁移已存在: {total_updated} 个")
    print(f"失败订阅源: {len(failed_feeds)} 个")
    for ff in failed_feeds:
        print(f"  - {ff['title']}: {ff['error']}")


if __name__ == "__main__":
    run_import()
