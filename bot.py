import os
import re
import json
import html
import hashlib
from datetime import datetime, timedelta, timezone

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

    start_str = start.strftime("%Y%m%d%H%M%S")
    end_str = now.strftime("%Y%m%d%H%M%S")

    query = """
    (
      (iran OR iranian OR tehran OR "islamic revolutionary guard corps" OR irgc)
      AND
      (war OR conflict OR strike OR airstrike OR missile OR drone OR military OR retaliation OR attack)
    )
    """.strip()

    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": "30",
        "format": "json",
        "sort": "DateDesc",
        "startdatetime": start_str,
        "enddatetime": end_str,
    }

    from urllib.parse import urlencode
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)


def fetch_articles() -> list[dict]:
    url = gdelt_query_url()
    resp = requests.get(url, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    return data.get("articles", [])


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_url(url: str) -> str:
    if not url:
        return ""
    return url.split("?")[0].strip().lower()


def clean_articles(raw_articles: list[dict]) -> list[dict]:
    cleaned = []
    seen = set()

    source_whitelist = {
        "reuters", "apnews", "bbc", "aljazeera", "cnn",
        "ft", "nytimes", "washingtonpost", "theguardian",
        "bloomberg", "cnbc", "wsj"
    }

    for a in raw_articles:
        title = normalize_text(a.get("title", ""))
        url = normalize_url(a.get("url", ""))
        source = normalize_text(a.get("sourceCommonName", "") or a.get("domain", ""))
        seendate = normalize_text(a.get("seendate", ""))

        if not title or not url:
            continue

        dedupe_key = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        score = 0
        lowered_source = source.lower()

        if any(s in lowered_source for s in source_whitelist):
            score += 3

        if any(k in title.lower() for k in ["iran", "iranian", "tehran", "irgc"]):
            score += 2

        if any(k in title.lower() for k in ["missile", "drone", "strike", "attack", "retaliation", "war"]):
            score += 2

        cleaned.append({
            "title": title,
            "url": url,
            "source": source or "Unknown",
            "seendate": seendate,
            "score": score,
        })

    cleaned.sort(key=lambda x: (x["score"], x["seendate"]), reverse=True)
    return cleaned[:8]


def make_openai_summary(articles: list[dict]) -> dict:
    if not articles:
        return {
            "summary_title": "이란 전쟁 관련 시간대 브리핑",
            "summary_lines": ["지난 1시간 기준으로 두드러진 신규 기사 포착이 없습니다."],
            "article_lines": [],
        }

    article_text = "\n".join(
        [
            f"{i+1}. 제목: {a['title']}\n출처: {a['source']}\n링크: {a['url']}"
            for i, a in enumerate(articles)
        ]
    )

    prompt = f"""
너는 국제뉴스 브리핑 에디터다.
아래 기사 목록만 근거로, 한국어로 매우 간결하게 브리핑을 작성해라.

출력 규칙:
- 반드시 JSON 객체만 출력
- 키는 summary_title, summary_lines, article_lines
- summary_title: 1줄 문자열
- summary_lines: 문자열 배열 3개 이하
- article_lines: 문자열 배열 최대 5개
- 추측 금지
- 기사에 없는 내용 단정 금지
- 서로 비슷한 내용은 합쳐라
- 전문용어보다 자연스러운 한국어 사용
- 톤은 건조한 브리핑체
- article_lines 각 항목은 다음 형식:
  "• [출처] 한글 한줄 요약"

기사 목록:
{article_text}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    text = response.output_text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "summary_title": "이란 전쟁 관련 시간대 브리핑",
            "summary_lines": ["모델 응답 파싱에 실패해 기사 원문 제목 기준으로 전달합니다."],
            "article_lines": [f"• [{a['source']}] {a['title']}" for a in articles[:5]],
        }

    return data


def build_message(summary: dict, articles: list[dict]) -> str:
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"🛰 {summary.get('summary_title', '이란 전쟁 관련 시간대 브리핑')}",
        f"기준시각: {now_kst} KST",
        "",
    ]

    for item in summary.get("summary_lines", []):
        lines.append(f"- {item}")

    if summary.get("article_lines"):
        lines.append("")
        lines.append("주요 기사:")
        for item in summary["article_lines"][:5]:
            lines.append(item)

    if articles:
        lines.append("")
        lines.append("원문 링크:")
        for idx, a in enumerate(articles[:5], 1):
            lines.append(f"{idx}. {a['url']}")

    return "\n".join(lines)


def send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=40)
    resp.raise_for_status()


def main() -> None:
    articles = fetch_articles()
    articles = clean_articles(articles)
    summary = make_openai_summary(articles)
    message = build_message(summary, articles)
    send_telegram_message(message)


if __name__ == "__main__":
    main()
