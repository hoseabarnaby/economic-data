from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import urlencode, quote
import requests
import os
import base64
import datetime
import re
import xml.etree.ElementTree as ET

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ==========================================
# KONFIGURASI SUPABASE (DARI VERCEL ENV VARS)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://gwkqmhsmlmmzcmqcqpft.supabase.co")
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd3a3FtaHNtbG1temNtcWNxcGZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwMDYwMzcsImV4cCI6MjEwODU4MjAzN30.AXKbMO3dQw8mEWbmDsSVxSMMjthBxyJWfZUpC8_afWI"
)

# ─────────────────────────────────────────────────────────────
# DAFTAR RSS FEED (GRATIS, TANPA API KEY, RELIABLE)
# ─────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {"url": "https://www.antaranews.com/rss/ekonomi.xml", "source": "Antara News"},
    {"url": "https://finance.detik.com/rss",               "source": "Detik Finance"},
    {"url": "https://www.cnbcindonesia.com/rss",          "source": "CNBC Indonesia"},
    {"url": "https://biz.kompas.com/rss",                 "source": "Kompas Ekonomi"},
]


# ==========================================
# ENDPOINT KONFIGURASI
# ==========================================
@app.get("/api/config")
def get_config():
    """
    Endpoint ini dipanggil oleh index.html dan admin.html
    untuk mendapatkan URL dan Anon Key Supabase secara aman.
    """
    return {
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": SUPABASE_ANON_KEY
    }


@app.get("/api/inflasi")
def get_inflasi():
    return {"nilai": 2.56, "tahun": 2026}


# ==========================================
# ENDPOINT AI CHAT
# ==========================================
class ChatRequest(BaseModel):
    message: str
    context: str


@app.post("/api/chat")
def chat_with_deepseek(req: ChatRequest):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="API Key DeepSeek belum diatur di Vercel.")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = (
        f"Anda adalah AI Economic Insight, asisten analis keuangan cerdas.\n"
        f"Data konteks: {req.context}"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.message}
        ],
        "stream": False
    }

    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return {"reply": response.json()['choices'][0]['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal: {str(e)}")


# ==========================================
# HELPER: FETCH RSS FEEDS
# ==========================================
def fetch_rss_articles(max_per_feed: int = 8):
    """
    Ambil berita dari beberapa RSS feed Indonesia.
    Return list artikel siap diproses.
    """
    articles = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; EconomicInsightBot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed["url"], timeout=4, headers=headers)
            if r.status_code != 200:
                print(f"[RSS] {feed['source']} -> HTTP {r.status_code}")
                continue

            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//atom:entry", ns)

            for item in items[:max_per_feed]:
                try:
                    if item.tag.endswith("item"):  # RSS 2.0
                        title   = (item.findtext("title") or "").strip()
                        link    = (item.findtext("link") or "").strip()
                        desc    = (item.findtext("description") or "").strip()
                        pubdate = (item.findtext("pubDate") or "").strip()
                        enclos  = item.find("enclosure")
                        image   = enclos.get("url") if enclos is not None else ""
                    else:  # Atom
                        title   = (item.findtext("atom:title", default="", namespaces=ns) or "").strip()
                        link_el = item.find("atom:link", ns)
                        link    = link_el.get("href") if link_el is not None else ""
                        desc    = (item.findtext("atom:summary", default="", namespaces=ns) or "").strip()
                        pubdate = (item.findtext("atom:updated", default="", namespaces=ns) or "").strip()
                        image   = ""

                    if not title or not link:
                        continue

                    # Bersihkan HTML dari description
                    desc_clean = re.sub(r"<[^>]+>", "", desc).strip()

                    articles.append({
                        "title": title,
                        "url": link,
                        "content": desc_clean,
                        "description": desc_clean[:500],
                        "image": image,
                        "source": feed["source"],
                        "published_at": pubdate or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    })
                except Exception as item_err:
                    print(f"[RSS] skip item: {item_err}")
                    continue

        except Exception as e:
            print(f"[RSS] {feed['source']} error: {e}")
            continue

    return articles


# ==========================================
# ENDPOINT SYNC BERITA
# ==========================================
@app.get("/api/news/sync")
def sync_news():
    """
    Sync berita dari RSS feed, simpan yang baru ke Supabase.
    Return JSON dengan info yang jelas + HTTP error code yang benar.
    """
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY belum diset di Vercel.")

    headers_supabase = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    # ─── 1. Ambil semua berita dari RSS ────────────────────────
    try:
        articles = fetch_rss_articles(max_per_feed=8)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal fetch RSS: {e}")

    if not articles:
        return {
            "status": "success",
            "inserted": 0,
            "message": "Tidak ada artikel dari RSS saat ini.",
        }

    # ─── 2. Batch cek duplikat (1 request, bukan N request) ────
    all_urls = [a["url"] for a in articles]
    existing_urls = set()
    try:
        urls_param = "(" + ",".join(quote(u, safe="") for u in all_urls) + ")"
        check_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_archive?select=original_url&original_url=in.{urls_param}",
            headers=headers_supabase,
            timeout=5,
        )
        if check_res.status_code == 200:
            existing_urls = {row["original_url"] for row in check_res.json()}
        else:
            print(f"[Supabase] batch check HTTP {check_res.status_code}: {check_res.text[:200]}")
    except Exception as e:
        print(f"[Supabase] batch cek duplikat gagal: {e}")

    new_articles = [a for a in articles if a["url"] not in existing_urls]

    if not new_articles:
        return {
            "status": "success",
            "inserted": 0,
            "checked": len(articles),
            "message": f"Semua {len(articles)} artikel sudah ada di database.",
        }

    # ─── 3. Proses maksimal 3 artikel baru per sync (anti timeout) ─
    inserted_count = 0
    errors = []

    for article in new_articles[:3]:
        try:
            content = (article.get("content") or article.get("description") or "")[:2500]

            # Minta ringkasan ke DeepSeek (fallback ke konten asli kalau gagal)
            summary = content or article["title"]
            if content:
                ai_payload = {
                    "model": "deepseek-chat",
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Ringkas berita ini dalam 2 paragraf singkat (maks 120 kata):\n"
                            f"Judul: {article['title']}\nKonten: {content}"
                        ),
                    }],
                    "max_tokens": 250,
                }
                try:
                    ai_res = requests.post(
                        "https://api.deepseek.com/chat/completions",
                        json=ai_payload,
                        headers={
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        timeout=8,
                    )
                    ai_res.raise_for_status()
                    summary = ai_res.json()["choices"][0]["message"]["content"]
                except Exception as ai_err:
                    print(f"[AI] fallback ke konten asli: {ai_err}")

            # ─── Deteksi kategori ─────────────────────────
            text_lower = (article["title"] + " " + content).lower()
            category = "umum"
            if any(k in text_lower for k in ["pangan", "beras", "cabai", "daging", "telur", "gula"]):
                category = "pangan"
            elif any(k in text_lower for k in ["saham", "ihsg", "rupiah", "kurs", "bank", "investasi"]):
                category = "keuangan"
            elif any(k in text_lower for k in ["bbm", "minyak", "gas", "listrik", "energi"]):
                category = "energi"
            elif any(k in text_lower for k in ["pajak", "apbn", "fiskal", "bi rate", "inflasi"]):
                category = "kebijakan"

            slug = base64.urlsafe_b64encode(article["url"].encode()).decode()[:40]

            data = {
                "slug": slug,
                "title": article["title"],
                "description": article["description"][:300],
                "summary": summary,
                "image_url": article.get("image") or "",
                "source_name": article.get("source", "Media"),
                "original_url": article["url"],
                "published_at": article.get("published_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "category": category,
            }

            insert_res = requests.post(
                f"{SUPABASE_URL}/rest/v1/news_archive",
                json=data,
                headers=headers_supabase,
                timeout=5,
            )

            if insert_res.status_code in (200, 201):
                inserted_count += 1
            else:
                errors.append(
                    f"{article['title'][:30]}... -> HTTP {insert_res.status_code}: {insert_res.text[:120]}"
                )

        except Exception as e:
            errors.append(str(e))
            continue

    # ─── 4. Return info yang jelas ─────────────────────────────
    return {
        "status": "success" if inserted_count > 0 else ("partial" if errors else "no_new"),
        "inserted": inserted_count,
        "checked": len(articles),
        "new_found": len(new_articles),
        "errors": errors[:3] if errors else [],
        "message": (
            f"{inserted_count} berita baru disimpan."
            if inserted_count
            else "Tidak ada berita baru yang berhasil disimpan."
        ),
    }


# ==========================================
# ENDPOINT PREVIEW LINK (SHARE)
# ==========================================
@app.get("/api/preview")
def preview_link(id: str = ""):
    if not id:
        return HTMLResponse(content="<h1>Link Tidak Valid</h1>", status_code=400)

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
    }
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/share_links?id=eq.{id}",
            headers=headers,
            timeout=5
        )
        data = res.json()
        if not data or len(data) == 0:
            return HTMLResponse(content="<h1>Berita tidak ditemukan</h1>", status_code=404)

        news = data[0]
        title = news.get('title', 'Economic Insight')
        desc = news.get('description', 'Baca berita ekonomi terbaru.')
        img = news.get('image_url', '')

        if img.startswith('http://'):
            img = img.replace('http://', 'https://')

        redirect_url = f"https://economic-data-lake.vercel.app/?{urlencode({'news_url': news.get('original_url'), 'title': title, 'desc': desc, 'img': img})}"

        html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:image" content="{img}" />
    <meta property="og:url" content="{redirect_url}" />
    <meta property="og:type" content="article" />
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">
    <meta name="twitter:image" content="{img}">
    <meta http-equiv="refresh" content="0; url={redirect_url}" />
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; background-color: #f8fafc;">
    <div style="text-align:center;">
        <h3>Membuka berita di Economic Insight...</h3>
        <p><a href="{redirect_url}">Klik di sini jika tidak dialihkan</a></p>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)


# ==========================================
# ENDPOINT ROOT
# ==========================================
@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
