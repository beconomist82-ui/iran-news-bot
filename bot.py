import os
import requests
from datetime import datetime, timedelta, timezone
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
        data = res.json()
        return data.get("articles", []), None
    except Exception:
        return [], "뉴스 가져오기 실패"


def summarize(articles, error):
    if error:
        return error

    if not articles:
        return "최근 1시간 주요 뉴스 없음"

    text = "\n".join([a["title"] for a in articles])

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=f"다음 뉴스 제목들을 한국어로 3줄 요약:\n{text}",
        )
        return response.output_text.strip()
    except Exception:
        return text


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})


def main():
    articles, error = fetch_news()
    summary = summarize(articles, error)

    now = datetime.now(KST).strftime("%H:%M")

    message = f"🛰 이란 뉴스 브리핑 ({now})\n\n{summary}"

    send(message)


if __name__ == "__main__":
    main()
