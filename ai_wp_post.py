from openai import OpenAI
import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import base64
import json

from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME")
WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD")

# === 設定項目（変更してください） ===
WORDPRESS_API_URL = "https://in-house.co.jp/ai/wp-json/wp/v2/posts"
WORDPRESS_MEDIA_API = "https://in-house.co.jp/ai/wp-json/wp/v2/media"
DEFAULT_CATEGORY_ID = 1
PRODUCT_HUNT_RSS = "https://www.producthunt.com/feed"

# カテゴリ名 → IDマップ
category_name_to_id = {
    "画像生成AI": 3,
    "チャット・対話AI": 4,
    "音声合成・認識AI": 5,
    "SNS分析・マーケティングAI": 6,
    "ライティング支援AI": 7,
    "プログラミング支援AI": 8,
    "その他": 1
}

# カテゴリ別デフォルト画像URLマップ
category_name_to_default_image = {
    "画像生成AI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/image-generation-scaled-e1749025087348.jpeg",
    "チャット・対話AI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/chat-scaled.jpeg",
    "音声合成・認識AI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/voice-scaled-e1749024908999.jpeg",
    "SNS分析・マーケティングAI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/sns-e1749024963907.jpeg",
    "ライティング支援AI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/writing-scaled-e1749025018331.jpeg",
    "プログラミング支援AI": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/programming-scaled-e1749025048816.jpeg",
    "その他": "https://in-house.co.jp/ai/wp-content/uploads/2025/06/others-scaled-e1749024735357.jpeg"
}

client = OpenAI(api_key=OPENAI_API_KEY)

def get_og_image(url):
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
    except Exception as e:
        print("OGP画像取得失敗:", e)
    return None

def upload_image_to_wordpress(image_url):
    try:
        img_data = requests.get(image_url).content
        filename = image_url.split("/")[-1]
        headers = {
            "Authorization": "Basic " + base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode()).decode(),
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "image/jpeg",
        }
        res = requests.post(WORDPRESS_MEDIA_API, headers=headers, data=img_data)
        res.raise_for_status()
        return res.json()["id"]
    except Exception as e:
        print("画像アップロード失敗:", e)
        return None

feed = feedparser.parse(PRODUCT_HUNT_RSS)
latest_entries = feed.entries[:3]

for entry in latest_entries:
    raw_service_name = entry.title
    link = entry.link

    # タイトル・meta description生成
    title_meta_prompt = f"""
以下のAIサービスについて、SEOに強い日本語タイトル（32文字以内）とmeta description（100〜120文字）を作ってください。
※コードブロック（```など）やMarkdownは禁止。プレーンテキストで出力。

【出力形式】
タイトル：◯◯
meta description：△△

サービス名: {raw_service_name}
URL: {link}
"""
    title_meta_res = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": "あなたは日本語のSEOライターです。"},
            {"role": "user", "content": title_meta_prompt}
        ]
    )
    tm_text = title_meta_res.choices[0].message.content.strip()
    lines = [line for line in tm_text.split("\n") if "タイトル" in line or "meta description" in line]
    generated_title = next((line.replace("タイトル：", "").strip() for line in lines if "タイトル" in line), "タイトル取得失敗")
    generated_description = next((line.replace("meta description：", "").strip() for line in lines if "meta description" in line), "")

    # 記事本文生成
    content_prompt = f"""
以下のAIサービスについて、HTML構造で800〜1000字程度の日本語記事を作成してください。
構成：<h3>、<p>、<ul><li>のみ使用。Markdownやコードブロックは禁止。

<h2>{generated_title}</h2>
<h3>✅ 概要</h3>
<p>...</p>
<h3>🔍 主な機能と特徴</h3>
<ul><li>...</li></ul>
<h3>👀 こんな人におすすめ</h3>
<p>...</p>
<h3>💬 GPTコメント</h3>
<p>...</p>
<p>🔗 <a href=\"{link}\" target=\"_blank\" rel=\"noopener\">公式ページを見る</a></p>
"""
    content_res = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": "あなたは日本語のテック記事ライターです。"},
            {"role": "user", "content": content_prompt}
        ]
    )
    post_content = content_res.choices[0].message.content.strip().replace("```html", "").replace("```", "").replace("`", "").strip()

    # カテゴリ分類
    category_prompt = f"""
以下のAIサービスについて、次のカテゴリの中から最も近いものを1つだけ選んでください。日本語でカテゴリ名のみを返してください：

- 画像生成AI
- チャット・対話AI
- 音声合成・認識AI
- SNS分析・マーケティングAI
- ライティング支援AI
- プログラミング支援AI
- その他

サービス名: {raw_service_name}
説明: {generated_description}
"""
    category_res = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": "あなたはAI分野に詳しいWeb編集者です。"},
            {"role": "user", "content": category_prompt}
        ]
    )
    category_name = category_res.choices[0].message.content.strip()
    category_id = category_name_to_id.get(category_name, DEFAULT_CATEGORY_ID)

    # OGP画像 or カテゴリ画像
    image_url = get_og_image(link) or category_name_to_default_image.get(category_name, category_name_to_default_image["その他"])
    featured_media_id = upload_image_to_wordpress(image_url)

    # 本文に画像挿入
    post_content = f'<p><img src="{image_url}" alt="{generated_title}"></p>\n\n' + post_content

    # 投稿データ作成
    post_data = {
        "title": generated_title,
        "content": post_content,
        "status": "publish",
        "categories": [category_id],
        "featured_media": featured_media_id,
        "meta": {
            "meta_description": generated_description
        }
    }
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode()).decode(),
        "Content-Type": "application/json"
    }
    response = requests.post(WORDPRESS_API_URL, json=post_data, headers=headers)
    print(f"[{datetime.now()}] 投稿完了: {generated_title} / カテゴリ: {category_name} / ステータス: {response.status_code}")
