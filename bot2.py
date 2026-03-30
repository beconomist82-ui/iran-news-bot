import os
import requests
from datetime import datetime, timezone, timedelta
from openai import OpenAI

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)
KST = timezone(timedelta(hours=9))


def fetch_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "iran war OR iran israel conflict",
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
    except Exception:
        return []


def summarize(articles):
    if not articles:
        return "최근 뉴스 없음"

    titles = "\n".join([a.get("title", "") for a in articles if a.get("title")])

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=f"다음 뉴스 제목들을 한국어로 3줄로 간단히 요약해줘.\n{titles}",
        )
        return response.output_text.strip()
    except Exception:
        return titles or "요약 실패"


def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )


def main():
    articles = fetch_news()
    summary = summarize(articles)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    message = f"🛰 이란 뉴스 브리핑\n기준시각: {now} KST\n\n{summary}"

    if articles:
        links = []
        for i, article in enumerate(articles[:3], 1):
            url = article.get("url")
            if url:
                links.append(f"{i}. {url}")
        if links:
            message += "\n\n원문 링크:\n" + "\n".join(links)

    send_message(message)


if __name__ == "__main__":
    main()
