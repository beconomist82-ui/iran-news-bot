import os
import requests
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

KST = timezone(timedelta(hours=9))


def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "iran war OR iran israel conflict OR iran missile OR iran strike",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "apiKey": NEWS_API_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code != 200:
            return []
        data = res.json()
        return data.get("articles", [])
    except:
        return []


def summarize_with_gemini(articles):
    if not articles:
        return "- 최근 주요 뉴스가 없습니다."

    titles = "\n".join([a["title"] for a in articles if a.get("title")])

    prompt = f"""
다음은 이란 전쟁 관련 뉴스 제목이다.

조건:
- 반드시 한국어로 작성
- 3줄 요약
- 각 줄은 "- "로 시작
- 짧고 명확하게

뉴스:
{titles}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    try:
        res = requests.post(url, json=body, timeout=20)
        data = res.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()

    except Exception:
        return "- 한국어 요약 생성 실패"


def build_message(summary, articles):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    msg = f"🛰 이란 뉴스 브리핑\n기준시각: {now} KST\n\n{summary}"

    links = []
    for i, a in enumerate(articles[:3], 1):
        if a.get("url"):
            links.append(f"{i}. {a['url']}")

    if links:
        msg += "\n\n원문 링크:\n" + "\n".join(links)

    return msg


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True
    })


def main():
    articles = fetch_news()
    summary = summarize_with_gemini(articles)
    message = build_message(summary, articles)
    send(message)


if __name__ == "__main__":
    main()
