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
        "q": "iran war OR iran israel conflict OR iran strike OR iran missile",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "apiKey": NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code != 200:
            return [], f"NewsAPI 오류: HTTP {response.status_code}"
        data = response.json()
        return data.get("articles", []), None
    except Exception as e:
        return [], f"NewsAPI 호출 실패: {str(e)}"


def summarize(articles):
    if not articles:
        return "- 최근 주요 뉴스가 없습니다.", None

    titles = []
    for article in articles:
        title = article.get("title")
        if title:
            titles.append(title)

    if not titles:
        return "- 최근 주요 뉴스가 없습니다.", None

    joined_titles = "\n".join(titles)

    prompt = f"""
아래는 이란 전쟁 관련 영어 뉴스 제목들이다.

반드시 다음 규칙을 지켜라.
1. 답변은 한국어로만 작성할 것
2. 정확히 3개의 불릿만 작성할 것
3. 각 줄은 "- "로 시작할 것
4. 짧고 자연스러운 한국어 브리핑 문장으로 쓸 것
5. 영어 제목을 그대로 복사하지 말 것
6. 추측하지 말고 제목에 있는 내용만 바탕으로 요약할 것

뉴스 제목:
{joined_titles}
"""

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt,
        )

        text = (response.output_text or "").strip()
        if not text:
            return "- 한국어 요약 결과가 비어 있습니다.", "OpenAI 응답은 왔지만 output_text가 비어 있음"

        return text, None

    except Exception as e:
        return "- 한국어 요약 생성에 실패했습니다.", f"OpenAI 오류: {str(e)}"


def build_message(summary, articles, news_error=None, summary_error=None):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    message = f"🛰 이란 뉴스 브리핑\n기준시각: {now} KST\n\n{summary}"

    links = []
    for index, article in enumerate(articles[:3], 1):
        url = article.get("url")
        if url:
            links.append(f"{index}. {url}")

    if links:
        message += "\n\n원문 링크:\n" + "\n".join(links)

    if news_error or summary_error:
        message += "\n\n[디버그]"
        if news_error:
            message += f"\n- {news_error}"
        if summary_error:
            message += f"\n- {summary_error}"

    return message


def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload, timeout=20)


def main():
    articles, news_error = fetch_news()
    summary, summary_error = summarize(articles)
    message = build_message(summary, articles, news_error, summary_error)
    send_message(message)


if __name__ == "__main__":
    main()
