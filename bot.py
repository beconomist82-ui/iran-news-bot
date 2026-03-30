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
    except:
        return []


def summarize(articles):
    if not articles:
        return "최근 뉴스 없음"

    titles = "\n".join([a["title"] for a in articles])

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=f"다음 뉴스들을 한국어로 3줄 요약:\n{titles}",
        )
        return response.output_text.strip()
    except:
        return titles


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})


def main():
    articles = fetch_news()
    summary = summarize(articles)

    now = datetime.now(KST).strftime("%H:%M")

    message = f"🛰 이란 뉴스 브리핑 ({now})\n\n{summary}"

    send(message)


if __name__ == "__main__":
    main()
