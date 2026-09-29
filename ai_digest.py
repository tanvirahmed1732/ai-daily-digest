"""Daily AI news digest. Local Windows version.

Fetches HN + arXiv + HF Papers + RSS feeds, filters/groups, emails via Gmail SMTP.
Reads config from .env file in same directory.
"""

import html as html_lib
import json
import os
import re
import smtplib
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / "config.env"
LOG_FILE = HERE / "last_run.log"
SENT_FILE = HERE / "last_sent.txt"


def load_env():
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}. Copy config.env.example to config.env and fill in your values (see README.md).")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

SENDER = os.environ["GMAIL_SENDER"]
APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
RECIPIENTS = [e.strip() for e in os.environ["GMAIL_RECIPIENTS"].split(",")]
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

TZ_OFFSET_HOURS = float(os.environ.get("TIMEZONE_OFFSET_HOURS", "6") or "6")
TZ_LABEL = os.environ.get("TIMEZONE_LABEL", "").strip() or f"UTC{TZ_OFFSET_HOURS:+g}"
LOCAL_TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))
TODAY = datetime.now(LOCAL_TZ)
TODAY_STR = TODAY.strftime("%Y-%m-%d")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_AI_CONTEXT = {
    "ai", "llm", "gpt", "claude", "gemini", "bert", "llama", "mistral", "qwen",
    "language model", "neural", "machine learning", "deep learning", "transformer",
    "diffusion", "inference", "anthropic", "openai", "deepmind", "hugging face",
    "foundation model", "embedding", "fine-tun", "weights", "parameter",
}
_WEAK_KEYWORDS = {"model", "agent", "training", "weights"}

RSS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("VentureBeat AI", "https://feeds.feedburner.com/venturebeat/SZYF"),
    ("KDnuggets", "https://www.kdnuggets.com/feed"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    # Anthropic has no official feed; community mirror of anthropic.com/news
    ("Anthropic Blog", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml"),
    ("DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/"),
    ("Microsoft AI Blog", "https://news.microsoft.com/source/topics/ai/feed/"),
    ("BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml"),
    ("Apple ML Research", "https://machinelearning.apple.com/rss.xml"),
    ("Meta AI Blog", "https://engineering.fb.com/category/ml-applications/feed/"),
    ("InfoQ AI", "https://feed.infoq.com/ai-ml-data-eng/"),
]


def log(msg):
    line = f"[{datetime.now().isoformat()}] {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def strip_html(text):
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def fetch_hn():
    try:
        top = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15).json()[:80]
        items = []
        for hid in top:
            try:
                it = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{hid}.json", timeout=10).json()
                if not it:
                    continue
                title = (it.get("title") or "")
                t_low = title.lower()
                _hn_strong = ("ai", "llm", "gpt", "claude", "gemini", "anthropic", "openai", "deepmind", "ml ", "neural", "rag", "transformer", "diffusion", "mistral", "llama", "qwen", "language model", "foundation model")
                _hn_weak = ("model", "agent")
                has_strong = any(k in t_low for k in _hn_strong)
                has_weak = any(k in t_low for k in _hn_weak)
                if not has_strong and not has_weak:
                    continue
                if not has_strong and has_weak:
                    if not any(ctx in t_low for ctx in _AI_CONTEXT):
                        continue
                items.append({
                    "source": "HackerNews",
                    "title": title,
                    "url": it.get("url") or f"https://news.ycombinator.com/item?id={hid}",
                    "permalink": f"https://news.ycombinator.com/item?id={hid}",
                    "selftext": "",
                    "score": it.get("score", 0),
                    "num_comments": it.get("descendants", 0),
                    "created_utc": it.get("time", 0),
                })
            except Exception:
                continue
            time.sleep(0.03)
        return items
    except Exception as e:
        log(f"[hn] error: {e}")
        return []


def fetch_rss(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            log(f"[rss {name}] HTTP {r.status_code}")
            return []
        root = ET.fromstring(r.content)
        items = []
        cutoff = time.time() - 48 * 3600
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            date_el = item.find("pubDate")
            if title_el is None or link_el is None:
                continue
            title = (title_el.text or "").strip()
            link = (link_el.text or "").strip()
            desc = (desc_el.text or "").strip() if desc_el is not None else ""
            desc = strip_html(desc)
            ts = 0
            if date_el is not None and date_el.text:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = parsedate_to_datetime(date_el.text).timestamp()
                except Exception:
                    ts = 0
            if ts and ts < cutoff:
                continue
            items.append({
                "source": name,
                "title": title,
                "url": link,
                "permalink": link,
                "selftext": (desc or "")[:600],
                "score": 0,
                "num_comments": 0,
                "created_utc": int(ts) if ts else int(time.time()),
            })
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title_el = entry.find("{http://www.w3.org/2005/Atom}title")
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
            published_el = entry.find("{http://www.w3.org/2005/Atom}published")
            if published_el is None:
                published_el = entry.find("{http://www.w3.org/2005/Atom}updated")
            if title_el is None or link_el is None:
                continue
            title = (title_el.text or "").strip()
            link = link_el.attrib.get("href", "").strip()
            desc = strip_html(summary_el.text or "") if summary_el is not None else ""
            ts = 0
            if published_el is not None and published_el.text:
                try:
                    ts = datetime.fromisoformat(published_el.text.replace("Z", "+00:00")).timestamp()
                except Exception:
                    ts = 0
            if ts and ts < cutoff:
                continue
            items.append({
                "source": name,
                "title": title,
                "url": link,
                "permalink": link,
                "selftext": (desc or "")[:600],
                "score": 0,
                "num_comments": 0,
                "created_utc": int(ts) if ts else int(time.time()),
            })
        return items
    except Exception as e:
        log(f"[rss {name}] error: {e}")
        return []


def fetch_hf_papers():
    try:
        r = requests.get("https://huggingface.co/api/daily_papers", headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            log(f"[hf_papers] HTTP {r.status_code}")
            return []
        data = r.json()
        items = []
        for p in data[:40]:
            paper = p.get("paper", {}) or {}
            pid = paper.get("id") or p.get("id") or ""
            title = paper.get("title") or p.get("title", "")
            summary = paper.get("summary") or p.get("summary", "")
            upvotes = paper.get("upvotes") or p.get("numViews") or 0
            published = p.get("publishedAt") or paper.get("publishedAt", "")
            ts = 0
            if published:
                try:
                    ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
                except Exception:
                    ts = 0
            items.append({
                "source": "HF Daily Papers",
                "title": title,
                "url": f"https://huggingface.co/papers/{pid}" if pid else "https://huggingface.co/papers",
                "permalink": f"https://huggingface.co/papers/{pid}" if pid else "https://huggingface.co/papers",
                "selftext": summary[:600],
                "score": upvotes,
                "num_comments": 0,
                "created_utc": int(ts) if ts else int(time.time()),
            })
        return items
    except Exception as e:
        log(f"[hf_papers] error: {e}")
        return []


def fetch_arxiv():
    cats = ["cs.AI", "cs.LG", "cs.CL"]
    items = []
    for cat in cats:
        try:
            url = f"http://export.arxiv.org/api/query?search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results=20"
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = (entry.find("a:title", ns).text or "").strip().replace("\n", " ")
                link = entry.find("a:id", ns).text.strip()
                summary = (entry.find("a:summary", ns).text or "").strip().replace("\n", " ")[:600]
                published = entry.find("a:published", ns).text
                items.append({
                    "source": f"arXiv/{cat}",
                    "title": title,
                    "url": link,
                    "permalink": link,
                    "selftext": summary,
                    "score": 0,
                    "num_comments": 0,
                    "created_utc": int(datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()),
                })
        except Exception as e:
            log(f"[arxiv {cat}] error: {e}")
    return items


def dedupe(items):
    seen = set()
    out = []
    for it in items:
        url_key = (it["url"] or "").split("?")[0].rstrip("/").lower()
        title_key = "".join(c for c in it["title"].lower() if c.isalnum())[:80]
        key = (url_key, title_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


FALLBACK_DROP = [
    "meme", "lol", "funny", "joke", "shitpost",
    "what do you think", "what do yall think", "what do you guys think",
    "how do i", "how to get started", "beginner", "newbie",
    "help me", "can someone", "is it just me",
    "hot take", "unpopular opinion",
    "cad model", "3d model", "scale model", "business model", "pricing model",
    "cooling fan", "heatsink", "heat sink", "3d print",
]

FALLBACK_KEEP = [
    "release", "releases", "launched", "announces", "announcing", "announce",
    "model", "benchmark", "paper", "research", "study",
    "api", "funding", "raised", "acquires", "acquisition", "ipo",
    "open source", "open-source", "open weights", "weights",
    "state of the art", "sota", "results", "outperforms",
    "gpu", "training", "dataset", "fine-tune", "fine tune",
    "agent", "agentic", "tool use", "function calling",
    "rag", "retrieval", "context window",
]

def heuristic_filter(items):
    out = []
    for it in items:
        t = it["title"].lower()
        if any(bad in t for bad in FALLBACK_DROP):
            continue
        if "arxiv" in it["source"].lower():
            out.append(it)
            continue
        matched = [kw for kw in FALLBACK_KEEP if kw in t]
        if it.get("score", 0) > 200 or matched:
            if matched and all(kw in _WEAK_KEYWORDS for kw in matched):
                if not any(ctx in t for ctx in _AI_CONTEXT):
                    continue
            out.append(it)
    return out


def heuristic_rank(items):
    now = time.time()
    for it in items:
        age_h = max(1, (now - it.get("created_utc", now)) / 3600)
        recency_bonus = 1.2 if age_h < 6 else (1.0 if age_h < 24 else 0.7)
        it["_rank"] = (it.get("score", 0) + it.get("num_comments", 0) * 2 + 50) * recency_bonus
    return sorted(items, key=lambda x: x["_rank"], reverse=True)


def heuristic_group(items):
    groups = {
        "Models & Releases": [],
        "Research": [],
        "Tools & Products": [],
        "Industry News": [],
        "Data Science & Analytics": [],
        "Community Insights": [],
    }
    for it in items[:30]:
        t = it["title"].lower()
        src = it["source"].lower()
        if "arxiv" in src or "hf daily" in src or "paper" in t or "study" in t:
            groups["Research"].append(it)
        elif any(k in t for k in ["release", "launched", "announces", "model", "weights", "api"]):
            groups["Models & Releases"].append(it)
        elif any(k in t for k in ["funding", "raised", "acquires", "acquisition", "ipo", "layoff"]):
            groups["Industry News"].append(it)
        elif "datascience" in src or "kdnuggets" in src or "analytics" in src or "statistics" in src or any(k in t for k in ["pandas", "numpy", "dashboard", "etl", "sql", "bi ", "analytics", "visualization", "dataset", "feature engineering"]):
            groups["Data Science & Analytics"].append(it)
        elif any(k in t for k in ["tool", "product", "app", "plugin", "extension"]):
            groups["Tools & Products"].append(it)
        else:
            groups["Community Insights"].append(it)
    return groups


def _build_prompt(items):
    trimmed = [
        {
            "source": it["source"],
            "title": it["title"][:200],
            "url": it["url"],
            "snippet": (it.get("selftext") or "")[:400],
            "score": it.get("score", 0),
            "comments": it.get("num_comments", 0),
        }
        for it in items[:200]
    ]
    return f"""You are a senior AI + data science news curator writing for a busy reader. Below is raw data from Hacker News, arXiv, Hugging Face Daily Papers, and major AI/tech news RSS feeds from the last 24-48 hours. Produce a high-signal, EASY-TO-UNDERSTAND daily digest.

RULES:
- KEEP only: new model releases (weights/API/benchmarks), research papers with concrete results, product launches/major updates, benchmark/eval results, industry news (funding/acquisitions/policy), notable technical insights backed by data.
- DROP: memes, jokes, shitposts, opinions without data, beginner questions, how-to-do-X, drama, hot takes, hype without substance, "what do you think" posts, self-promotion without novelty.
- Dedupe items covering the same story.
- Pick top 15-25 total.
- Group into 6 sections: Models & Releases / Research / Tools & Products / Industry News / Data Science & Analytics / Community Insights. Omit empty sections.
- For each item: bold headline (rewrite for clarity if needed in PLAIN ENGLISH — avoid jargon, explain what/why simply), 1-2 sentence summary that a non-expert can understand (what happened + why it matters in plain language), source link.
- Prefer clarity over technical accuracy. If jargon unavoidable, add a 3-5 word inline gloss.

OUTPUT FORMAT — return ONLY valid HTML, no markdown, no code fences, no preamble:

<p style="color:#555;font-size:14px;">AI Daily Digest — <strong>{TODAY_STR}</strong> ({TZ_LABEL}) — <strong>N items</strong>.</p>
<h2 style="border-bottom:2px solid #e74c3c;color:#c0392b;">Models &amp; Releases</h2>
<p><b>Headline</b><br>
Plain-English summary sentence.<br>
<a href="URL">Source — HackerNews, arXiv, or publication name</a></p>
... more items and sections ...
<hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">
<p style="color:#888;font-size:12px;">Sources: Hacker News, arXiv, Hugging Face Daily Papers, TechCrunch, Ars Technica, MIT Tech Review, The Verge, Wired, VentureBeat, KDnuggets, InfoQ, Google/OpenAI/Anthropic/DeepMind/Microsoft/Meta/Apple/AWS/BAIR/Hugging Face blogs.</p>

RAW DATA (JSON):
{json.dumps(trimmed, ensure_ascii=False)}
"""


def _strip_code_fence(html):
    html = html.strip()
    if html.startswith("```"):
        html = html.split("```", 2)[1]
        if html.startswith("html"):
            html = html[4:]
        html = html.rsplit("```", 1)[0].strip()
    return html


def gemini_curate(items):
    if not GEMINI_KEY:
        return None
    prompt = _build_prompt(items)
    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 32768},
    }
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        for attempt in range(3):
            try:
                r = requests.post(url, json=payload, timeout=180)
                if r.status_code == 200:
                    data = r.json()
                    html = data["candidates"][0]["content"]["parts"][0]["text"]
                    log(f"[gemini] success via {model} attempt {attempt + 1}")
                    return _strip_code_fence(html)
                if r.status_code in (429, 503):
                    wait = 2 ** attempt * 5
                    log(f"[gemini {model}] HTTP {r.status_code} attempt {attempt + 1}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                log(f"[gemini {model}] HTTP {r.status_code}: {r.text[:300]}")
                break
            except Exception as e:
                log(f"[gemini {model}] error: {e}")
                time.sleep(2 ** attempt * 3)
    log("[gemini] all models exhausted")
    return None


def anthropic_curate(items):
    if not ANTHROPIC_KEY:
        return None
    try:
        import anthropic
    except ImportError:
        log("anthropic package not installed; skipping")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = _build_prompt(items)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        return _strip_code_fence(resp.content[0].text)
    except Exception as e:
        log(f"[anthropic] error: {e}")
        return None


def llm_curate(items):
    return gemini_curate(items) or anthropic_curate(items)


def heuristic_html(groups):
    colors = {
        "Models & Releases": ("#e74c3c", "#c0392b"),
        "Research": ("#3498db", "#2980b9"),
        "Tools & Products": ("#2ecc71", "#27ae60"),
        "Industry News": ("#9b59b6", "#8e44ad"),
        "Data Science & Analytics": ("#1abc9c", "#16a085"),
        "Community Insights": ("#f39c12", "#e67e22"),
    }
    count = sum(len(v) for v in groups.values())
    parts = [f'<p style="color:#555;font-size:14px;">AI Daily Digest \u2014 <strong>{TODAY_STR}</strong> ({TZ_LABEL}) \u2014 <strong>{count} items</strong>.</p>']
    for name, items in groups.items():
        if not items:
            continue
        border, text = colors[name]
        parts.append(f'<h2 style="border-bottom:2px solid {border};color:{text};">{name}</h2>')
        for it in items:
            snippet = (it.get("selftext") or "")[:200]
            parts.append(
                f'<p><b>{it["title"]}</b><br>'
                f'{snippet}<br>'
                f'<a href="{it["url"]}">Source \u2014 {it["source"]}</a></p>'
            )
    parts.append('<hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">')
    parts.append('<p style="color:#888;font-size:12px;">Heuristic mode. Sources: Hacker News, arXiv, HF Papers, AI news &amp; lab blogs.</p>')
    return "\n".join(parts)


def send_email(html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AI Daily \u2014 {TODAY_STR}"
    msg["From"] = f"AI Daily Digest <{SENDER}>"
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SENDER, APP_PASSWORD)
        server.sendmail(SENDER, RECIPIENTS, msg.as_string())
    log(f"Sent to {RECIPIENTS}")


def already_sent_today():
    if not SENT_FILE.exists():
        return False
    return SENT_FILE.read_text(encoding="utf-8").strip() == TODAY_STR


def mark_sent():
    SENT_FILE.write_text(TODAY_STR, encoding="utf-8")


def main():
    if already_sent_today():
        log(f"Already sent today ({TODAY_STR}). Skipping.")
        return
    log(f"Starting digest for {TODAY_STR}")
    items = []
    hn = fetch_hn()
    log(f"HN: {len(hn)} items")
    items.extend(hn)

    arx = fetch_arxiv()
    log(f"arXiv: {len(arx)} items")
    items.extend(arx)

    hf = fetch_hf_papers()
    log(f"HF Daily Papers: {len(hf)} items")
    items.extend(hf)

    for name, url in RSS_FEEDS:
        feed_items = fetch_rss(name, url)
        log(f"{name}: {len(feed_items)} items")
        items.extend(feed_items)
        time.sleep(0.5)

    items = dedupe(items)
    log(f"After dedupe: {len(items)} items")

    html = llm_curate(items)
    if html:
        log("Using LLM-curated digest")
    else:
        log("Using heuristic digest")
        filtered = heuristic_filter(items)
        ranked = heuristic_rank(filtered)
        groups = heuristic_group(ranked)
        html = heuristic_html(groups)

    send_email(html)
    mark_sent()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        raise
