import os
import re
import json
import html
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from openai import OpenAI


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

KST = timezone(timedelta(hours=9))
UTC = timezone.utc


def gdelt_query_url() -> str:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=70)

    params = {
        "query": (
            '(iran OR iranian OR tehran OR irgc OR "islamic revolutionary guard corps") '
            'AND (war OR conflict OR strike OR airstrike OR missile OR drone OR attack OR retaliation)'
        ),
        "mode": "ArtList",
        "maxrecords": "10",
        "format": "json",
        "sort": "DateDesc",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": now.strftime("%Y%m%d%H%M%S"),
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str) -> str:
    if not url:
        return ""
    return url.split("?")[0].strip()


def fetch_articles():
    url = gdelt_query_url()

    try:
        resp = requests.get(
            url,
            timeout=40,
            headers={"User-Agent": "Mozilla/5.0 IranNewsBot/1.0"},
        )
    except requests.exceptions.Timeout:
        return [], "뉴스 서버 응답이 지연되었습니다."
    except requests.exceptions.RequestException:
        return [], "뉴스 수집 요청에 실패했습니다."

    if resp.status_code == 429:
        return [], "뉴스 서버 요청이 많아 잠시 제한되었습니다."

    if resp.status_code != 200:
        return [], f"뉴스 서버 오류가 발생했습니다. (HTTP {resp.status_code})"

    if not resp.text or not resp.text.strip():
        return [], "뉴스 응답이 비어 있습니다."

    try:
        data = resp.json()
    except Exception:
        return [], "뉴스 응답 형식이 비정상입니다."

    articles = data.get("articles", [])
    if not isinstance(articles, list):
        return [], "뉴스 데이터 구조가 예상과 다릅니다."

    return articles, None


def clean_articles(raw_articles):
    cleaned = []
    seen = set()

    trusted_sources = [
        "reuters", "bbc", "ap", "aljazeera", "bloomberg",
        "ft", "cnn", "nytimes", "wsj", "cnbc", "guardian"
    ]

    for article in raw_articles:
        title = normalize_text(article.get("title", ""))
        url = normalize_url(article.get("url", ""))
        source = normalize_text(article.get("sourceCommonName", "") or article.get("domain", ""))
        seendate = normalize_text(article.get("seendate", ""))

        if not title or not url:
            continue

        dedupe_key = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        score = 0
        lower_title = title.lower()
        lower_source = source.lower()

        if any(s in lower_source for s in trusted_sources):
            score += 3
        if any(k in lower_title for k in ["iran", "iranian", "tehran", "irgc"]):
            score += 2
        if any(k in lower_title for k in ["missile", "drone", "strike", "attack", "war", "retaliation"]):
            score += 2

        cleaned.append({
            "title": title,
            "url": url,
            "source": source or "Unknown",
            "seendate": seendate,
            "score": score,
        })

    cleaned.sort(key=lambda x: (x["score"], x["seendate"]), reverse=True)
    return cleaned[:5]


def summarize_in_korean(articles, error_message):
    if error_message:
        return {
            "summary_title": "이란 전쟁 관련 시간대 브리핑",
            "summary_lines": [error_message],
            "article_lines": [],
        }

    if not articles:
        return {
            "summary_title": "이란 전쟁 관련 시간대 브리핑",
            "summary_lines": ["지난 1시간 기준으로 두드러진 신규 기사가 없습니다."],
            "article_lines": [],
        }

    article_text = "\n".join(
        [
            f"{i+1}. 제목: {a['title']}\n출처: {a['source']}\n링크: {a['url']}"
            for i, a in enumerate(articles)
        ]
    )

    prompt = f"""
아래 기사 목록만 근거로 한국어 브리핑을 작성해라.

규칙:
- 반드시 JSON만 출력
- 키는 summary_title, summary_lines, article_lines
- summary_title은 문자열 1개
- summary_lines는 1~3개
- article_lines는 최대 5개
- 추측 금지
- 기사에 없는 내용 단정 금지
- 짧고 건조한 브리핑체
- article_lines 각 항목 형식:
  "• [출처] 한줄 요약"

기사 목록:
{article_text}
"""

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt,
        )
        text = response.output_text.strip()
        data = json.loads(text)
        return data
    except Exception:
        return {
            "summary_title": "이란 전쟁 관련 시간대 브리핑",
            "summary_lines": ["한글 요약 생성에 실패해 기사 제목 기준으로 전달합니다."],
            "article_lines": [f"• [{a['source']}] {a['title']}" for a in articles[:5]],
        }


def build_message(summary, articles):
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"🛰 {summary.get('summary_title', '이란 전쟁 관련 시간대 브리핑')}",
        f"기준시각: {now_kst} KST",
        "",
    ]

    for item in summary.get("summary_lines", []):
        lines.append(f"- {item}")

    article_lines = summary.get("article_lines", [])
    if article_lines:
        lines.append("")
        lines.append("주요 기사:")
        for item in article_lines[:5]:
            lines.append(item)

    if articles:
        lines.append("")
        lines.append("원문 링크:")
        for i, article in enumerate(articles[:5], 1):
            lines.append(f"{i}. {article['url']}")

    return "\n".join(lines)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=40)
    resp.raise_for_status()


def main():
    try:
        raw_articles, error_message = fetch_articles()
        articles = clean_articles(raw_articles)
        summary = summarize_in_korean(articles, error_message)
        message = build_message(summary, articles)
        send_telegram_message(message)
    except Exception as e:
        fallback = (
            "🛰 이란 전쟁 관련 시간대 브리핑\n"
            f"기준시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST\n\n"
            f"- 실행 중 오류가 발생했습니다: {str(e)[:200]}"
        )
        try:
            send_telegram_message(fallback)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
