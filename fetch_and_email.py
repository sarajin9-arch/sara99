"""
AI 교육 다이제스트 — 자동 수집 및 이메일 발송 스크립트
매일 오전 7시 GitHub Actions에서 자동 실행됩니다.

필요한 환경변수 (GitHub Secrets에 등록):
  GMAIL_USER     : 발송용 Gmail 주소 (예: yourname@gmail.com)
  GMAIL_APP_PASS : Gmail 앱 비밀번호 (16자리)
  RECIPIENT_EMAIL: 수신 이메일 주소 (네이버 등 어떤 주소든 가능)
"""

import os, json, smtplib, datetime, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
GMAIL_USER      = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASS", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

TODAY = datetime.date.today().strftime("%Y-%m-%d")
TODAY_KR = datetime.date.today().strftime("%Y년 %m월 %d일")

CATEGORIES = {
    "nursing":    {"label": "간호교육 AI",   "color": "#8b3a12", "bg": "#fde8d8"},
    "university": {"label": "대학교육 혁신", "color": "#1a4d6a", "bg": "#d8eaf5"},
    "fusion":     {"label": "융합교육",      "color": "#1a5235", "bg": "#d8f0e5"},
    "policy":     {"label": "정책·기관",     "color": "#3d2870", "bg": "#ede8f5"},
    "paper":      {"label": "학술논문",      "color": "#6a3010", "bg": "#f5ede8"},
}

# ──────────────────────────────────────────────
# 1. PubMed RSS 수집 (무료 API)
# ──────────────────────────────────────────────
PUBMED_QUERIES = [
    ("AI nursing education", "nursing"),
    ("artificial intelligence clinical nursing simulation", "nursing"),
    ("ChatGPT nursing students", "nursing"),
    ("LLM healthcare education", "paper"),
    ("AI university curriculum innovation", "university"),
    ("machine learning health professions education", "paper"),
]

def fetch_pubmed(query, category, max_results=3):
    articles = []
    try:
        encoded = urllib.parse.quote(query)
        search_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={encoded}&retmax={max_results}&sort=date&retmode=json"
            f"&mindate={TODAY}&maxdate={TODAY}"
        )
        # 날짜 범위 없이도 최신순 가져오기
        search_url2 = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={encoded}[Title/Abstract]&retmax={max_results}&sort=date&retmode=json"
        )
        with urllib.request.urlopen(search_url2, timeout=10) as r:
            data = json.loads(r.read())
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return articles

        ids_str = ",".join(ids)
        fetch_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={ids_str}&retmode=xml"
        )
        with urllib.request.urlopen(fetch_url, timeout=10) as r:
            xml_data = r.read()

        root = ET.fromstring(xml_data)
        for i, article in enumerate(root.findall(".//PubmedArticle")):
            title_el = article.find(".//ArticleTitle")
            title = title_el.text if title_el is not None else "제목 없음"
            if not title or len(title) < 10:
                continue

            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "https://pubmed.ncbi.nlm.nih.gov/"

            journal_el = article.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else "PubMed"

            year_el  = article.find(".//PubDate/Year")
            month_el = article.find(".//PubDate/Month")
            year  = year_el.text  if year_el  is not None else "2026"
            month = month_el.text if month_el is not None else "03"
            pub_date = f"{year}-{month}"

            abstract_el = article.find(".//AbstractText")
            abstract = abstract_el.text[:300] + "..." if abstract_el is not None and abstract_el.text else ""

            articles.append({
                "id": int(pmid) if pmid else i,
                "category": category,
                "tag": CATEGORIES[category]["label"],
                "title": title.strip("[]").strip(),
                "source": journal,
                "date": pub_date,
                "url": url,
                "summary": abstract,
            })
    except Exception as e:
        print(f"PubMed 수집 오류 ({query}): {e}")
    return articles

# ──────────────────────────────────────────────
# 2. Google Alerts RSS 수집 (무료)
# ──────────────────────────────────────────────
ALERT_FEEDS = [
    ("https://www.google.com/alerts/feeds/00000000000000000/AI+nursing+education", "nursing"),
    ("https://www.google.com/alerts/feeds/00135932185199891936/17966424033244388137", "university"),
    ("https://www.google.com/alerts/feeds/00135932185199891936/17966424033244386211", "fusion"),
    ("https://www.google.com/alerts/feeds/00135932185199891936/17966424033244386448", "policy"),
]
# ※ 위 URL은 예시입니다. 실제 Google Alerts 설정 후 발급받은 RSS URL로 교체하세요.
#   설정 방법: google.com/alerts → 키워드 입력 → "피드로 표시" 선택 → RSS 링크 복사

def fetch_rss(url, category, max_items=4):
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            xml_data = r.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns) or root.findall(".//item")

        for i, entry in enumerate(entries[:max_items]):
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el  = entry.find("atom:link",  ns) or entry.find("link")
            date_el  = entry.find("atom:updated", ns) or entry.find("pubDate")
            summary_el = entry.find("atom:summary", ns) or entry.find("description")

            title   = title_el.text if title_el is not None else "제목 없음"
            url_val = link_el.get("href", "") if link_el is not None else ""
            if not url_val and link_el is not None:
                url_val = link_el.text or ""
            date_str = date_el.text[:10] if date_el is not None and date_el.text else TODAY
            summary  = ""
            if summary_el is not None and summary_el.text:
                import html
                clean = html.unescape(summary_el.text)
                import re
                clean = re.sub('<[^>]+>', '', clean)[:250]
                summary = clean.strip()

            if not title or len(title) < 5:
                continue

            source = urllib.parse.urlparse(url_val).netloc.replace("www.", "") if url_val else "Google Alerts"

            articles.append({
                "id": hash(title) % 999999,
                "category": category,
                "tag": CATEGORIES[category]["label"],
                "title": title.strip(),
                "source": source,
                "date": date_str,
                "url": url_val,
                "summary": summary,
            })
    except Exception as e:
        print(f"RSS 수집 오류 ({url[:50]}): {e}")
    return articles

# ──────────────────────────────────────────────
# 3. 전체 수집 실행
# ──────────────────────────────────────────────
def collect_all():
    all_articles = []

    print("PubMed 논문 수집 중...")
    for query, cat in PUBMED_QUERIES:
        items = fetch_pubmed(query, cat, max_results=2)
        all_articles.extend(items)
        print(f"  '{query}' → {len(items)}건")

    print("RSS 피드 수집 중...")
    for feed_url, cat in ALERT_FEEDS:
        items = fetch_rss(feed_url, cat)
        all_articles.extend(items)
        print(f"  카테고리 '{cat}' → {len(items)}건")

    # 중복 제거 (제목 기준)
    seen_titles = set()
    unique = []
    for a in all_articles:
        key = a["title"][:60].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)

    # ID 재할당
    for i, a in enumerate(unique, 1):
        a["id"] = i

    print(f"\n총 {len(unique)}건 수집 완료 (중복 제거 후)")
    return unique

# ──────────────────────────────────────────────
# 4. data.json 저장 (웹앱에서 읽음)
# ──────────────────────────────────────────────
def save_json(articles):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print("data.json 저장 완료")

# ──────────────────────────────────────────────
# 5. 이메일 HTML 생성
# ──────────────────────────────────────────────
def build_email_html(articles):
    rows = ""
    for a in articles[:20]:  # 최대 20건
        cat = CATEGORIES.get(a["category"], CATEGORIES["paper"])
        rows += f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #e8e1d2;vertical-align:top">
            <span style="display:inline-block;background:{cat['bg']};color:{cat['color']};
              font-size:10px;font-weight:500;padding:2px 7px;border-radius:2px;
              margin-bottom:6px;letter-spacing:0.04em">{cat['label']}</span><br>
            <a href="{a['url']}" style="color:#1a1814;font-size:14px;font-weight:600;
              text-decoration:none;line-height:1.5;font-family:'Noto Serif KR',Georgia,serif">
              {a['title']}
            </a><br>
            <span style="font-size:11px;color:#7a756c;margin-top:4px;display:block">
              {a['source']} &nbsp;·&nbsp; {a['date']}
            </span>
            {f'<p style="font-size:12px;color:#3d3a34;margin:6px 0 0;line-height:1.7">{a["summary"]}</p>' if a.get("summary") else ""}
          </td>
        </tr>"""

    stats = {cat: sum(1 for a in articles if a["category"]==cat) for cat in CATEGORIES}
    stat_html = "".join(
        f'<td style="text-align:center;padding:10px 16px">'
        f'<div style="font-size:20px;font-weight:700;color:#b85c2a">{stats.get(c,0)}</div>'
        f'<div style="font-size:10px;color:#7a756c;margin-top:2px">{CATEGORIES[c]["label"]}</div></td>'
        for c in CATEGORIES
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=Noto+Sans+KR:wght@300;400;500&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#f0ebe0;font-family:'Noto Sans KR',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0ebe0;padding:24px 0">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#f8f5ef;border-top:4px solid #1a1814">

  <!-- Header -->
  <tr><td style="background:#1a1814;padding:24px 28px">
    <h1 style="margin:0;color:#f8f5ef;font-family:'Noto Serif KR',Georgia,serif;font-size:22px;font-weight:700">
      AI 교육 <span style="color:#b85c2a">다이제스트</span>
    </h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.5);font-size:11px">{TODAY_KR} &nbsp;·&nbsp; 자동 수집 리포트</p>
  </td></tr>

  <!-- Stats -->
  <tr><td style="padding:0;border-bottom:1px solid #e8e1d2">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>{stat_html}</tr></table>
  </td></tr>

  <!-- Articles -->
  <tr><td style="padding:0">
    <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#1a1814;padding:16px 28px;text-align:center">
    <p style="margin:0;color:rgba(255,255,255,0.4);font-size:10px;line-height:1.8">
      본 메일은 매일 오전 7시 자동 발송됩니다 · 백석문화대학교 간호학과<br>
      원문 확인 후 활용하시기 바랍니다
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

# ──────────────────────────────────────────────
# 6. 이메일 발송
# ──────────────────────────────────────────────
def send_email(articles):
    if not GMAIL_USER or not GMAIL_APP_PASS or not RECIPIENT_EMAIL:
        print("이메일 환경변수 미설정 — 발송 건너뜀")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[AI 교육 다이제스트] {TODAY_KR} — {len(articles)}건 수집"
    msg["From"]    = f"AI 교육 다이제스트 <{GMAIL_USER}>"
    msg["To"]      = RECIPIENT_EMAIL

    # 텍스트 버전
    text_body = f"AI 교육 다이제스트 {TODAY_KR}\n\n"
    for a in articles[:20]:
        text_body += f"[{CATEGORIES.get(a['category'],{}).get('label','기타')}] {a['title']}\n"
        text_body += f"  출처: {a['source']} · {a['date']}\n"
        text_body += f"  링크: {a['url']}\n\n"

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(build_email_html(articles), "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        print(f"이메일 발송 완료 → {RECIPIENT_EMAIL}")
    except Exception as e:
        print(f"이메일 발송 오류: {e}")

# ──────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== AI 교육 다이제스트 수집 시작 ({TODAY}) ===\n")
    articles = collect_all()
    save_json(articles)
    send_email(articles)
    print("\n=== 완료 ===")
