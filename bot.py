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
        "maxrecords": "15",
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
    return url.split("?")[0].strip().lower()


def fetch_articles() -> tuple[list[dict], str | None]:
    url = gdelt_query_url()

    try:
        resp = requests.get(
            url,
            timeout=40,
            headers={
                "User-Agent": "Mozilla/5.0 IranNewsBot/1.0"
            },
        )

        if resp.status_code == 429:
            return [], "뉴스 서버 요청이 많아 잠시 제한되었습니다."

        resp.raise_for_status()
        data = resp.json()
        return data.get("articles", []), None

    except requests.exceptions.Timeout:
        return [], "뉴스 서버 응답이 지연되었습니다."
    except requests.exceptions.RequestException:
        return [], "뉴스 수집 중 일시적인 오류가 발생했습니다."
    except Exception:
        return [], "뉴스 처리 중 알 수 없는 오류가 발생했습니다."


def clean_articles(raw_articles: list[dict]) -> list[dict]:
    cleaned = []
    seen = set()

    trusted_sources = [
        "reuters", "ap", "bbc", "aljazeera", "bloomberg",
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


def summarize_in_korean(articles: list[dict], error_message: str | None) -> dict:
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
- 키: summary_title, summary_lines, article_lines
- summary_title: 문자열 1개
- summary_lines: 1~3개
- article_lines: 최대 5개
- 추측 금지
- 없는 내용 단정 금지
- 한국어로 짧고 건조하게 요약
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
            "summary_lines": ["한글 요약 생성에 실패해 원문 제목 기준으로 전달합니다."],
            "article_lines": [f"• [{a['source']}] {a['title']}" for a in articles[:5]],
        }


def build_message(summary: dict, articles: list[dict]) -> str:
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
        for i, article in enumerate(articles[:5],
