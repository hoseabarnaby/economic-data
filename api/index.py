from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import urlencode, quote
import requests
import os
import base64
import hashlib
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

SUPABASE_URL = os.getenv("SUPABASE_URL", 'https://gwkqmhsmlmmzcmqcqpft.supabase.co')
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd3a3FtaHNtbG1temNtcWNxcGZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwMDYwMzcsImV4cCI6MjEwODU4MjAzN30.AXKbMO3dQw8mEWbmDsSVxSMMjthBxyJWfZUpC8_afWI'
)

RSS_FEEDS = [
    {"url": "https://www.antaranews.com/rss/ekonomi.xml", "source": "Antara News"},
    {"url": "https://finance.detik.com/rss",               "source": "Detik Finance"},
    {"url": "https://www.cnbcindonesia.com/rss",          "source": "CNBC Indonesia"},
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EconomicInsightBot/1.0)",
    "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
}


def make_slug(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


# ==========================================
# ENDPOINT CONFIG
# ==========================================
@app.get("/api/config")
def get_config():
    return {"supabaseUrl": SUPABASE_URL, "supabaseAnonKey": SUPABASE_ANON_KEY}


@app.get("/api/inflasi")
def get_inflasi():
    return {"nilai": 2.56, "tahun": 2026}


# ==========================================
# AI CHAT
# ==========================================
class ChatRequest(BaseModel):
    message: str
    context: str


@app.post("/api/chat")
def chat_with_deepseek(req: ChatRequest):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="API Key DeepSeek belum diatur di Vercel.")

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    system_prompt = f"Anda adalah AI Economic Insight, asisten analis keuangan cerdas.\nData konteks: {req.context}"
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
            json=payload, headers=headers, timeout=30
        )
        response.raise_for_status()
        return {"reply": response.json()['choices'][0]['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal: {str(e)}")


# ==========================================
# HELPER: FETCH RSS (content lengkap)
# ==========================================
def fetch_from_rss(max_per_feed=10):
    articles = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed["url"], timeout=5, headers=COMMON_HEADERS)
            if r.status_code != 200:
                print(f"[RSS] {feed['source']} -> HTTP {r.status_code}")
                continue

            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//atom:entry", ns)

            for item in items[:max_per_feed]:
                try:
                    if item.tag.endswith("item"):
                        title   = (item.findtext("title") or "").strip()
                        link    = (item.findtext("link") or "").strip()
                        desc    = (item.findtext("description") or "").strip()
                        pubdate = (item.findtext("pubDate") or "").strip()
                        enclos  = item.find("enclosure")
                        image   = enclos.get("url") if enclos is not None else ""
                    else:
                        title   = (item.findtext("atom:title", default="", namespaces=ns) or "").strip()
                        link_el = item.find("atom:link", ns)
                        link    = link_el.get("href") if link_el is not None else ""
                        desc    = (item.findtext("atom:summary", default="", namespaces=ns) or "").strip()
                        pubdate = (item.findtext("atom:updated", default="", namespaces=ns) or "").strip()
                        image   = ""

                    if not title or not link:
                        continue

                    # Bersihkan HTML tapi PERTAHANKAN paragraf
                    desc_clean = re.sub(r"<br\s*/?>", "\n", desc, flags=re.IGNORECASE)
                    desc_clean = re.sub(r"</p>", "\n\n", desc_clean, flags=re.IGNORECASE)
                    desc_clean = re.sub(r"<[^>]+>", "", desc_clean)
                    desc_clean = re.sub(r"\n{3,}", "\n\n", desc_clean).strip()

                    articles.append({
                        "title": title,
                        "url": link,
                        "content": desc_clean[:5000],       # ← ISI LENGKAP dari RSS
                        "description": desc_clean[:500],
                        "image": image,
                        "source": feed["source"],
                        "published_at": pubdate or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[RSS] {feed['source']} error: {e}")
            continue

    return articles


# ==========================================
# SYNC BERITA
# ==========================================
@app.get("/api/news/sync")
def sync_news():
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY belum diset di Vercel.")

    headers_supabase = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation",
    }

    try:
        articles = fetch_from_rss()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal fetch RSS: {e}")

    if not articles:
        return {"status": "success", "source": "rss", "inserted": 0, "message": "Tidak ada artikel dari RSS."}

    # Batch check duplikat
    all_urls = [a["url"] for a in articles]
    existing_urls = set()
    try:
        urls_param = "(" + ",".join(quote(u, safe="") for u in all_urls) + ")"
        check_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_archive?select=original_url&original_url=in.{urls_param}",
            headers={**headers_supabase, "Prefer": "return=representation"},
            timeout=6,
        )
        if check_res.status_code == 200:
            existing_urls = {row["original_url"] for row in check_res.json()}
    except Exception as e:
        print(f"[Supabase] batch check error: {e}")

    new_articles = [a for a in articles if a["url"] not in existing_urls]

    if not new_articles:
        return {
            "status": "success", "source": "rss", "inserted": 0,
            "checked": len(articles),
            "message": f"Semua {len(articles)} artikel sudah ada di database.",
        }

    inserted_count = 0
    insert_errors = []

    for article in new_articles[:3]:
        try:
            content = article.get("content") or article.get("description") or ""

            # AI Summary
            summary = content or article["title"]
            if content:
                ai_payload = {
                    "model": "deepseek-chat",
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Ringkas berita ini dalam 2 paragraf singkat (maks 120 kata):\n"
                            f"Judul: {article['title']}\nKonten: {content[:2500]}"
                        ),
                    }],
                    "max_tokens": 250,
                }
                try:
                    ai_res = requests.post(
                        "https://api.deepseek.com/chat/completions",
                        json=ai_payload,
                        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                        timeout=10,
                    )
                    ai_res.raise_for_status()
                    summary = ai_res.json()["choices"][0]["message"]["content"]
                except Exception as ai_err:
                    print(f"[AI] fallback: {ai_err}")

            # Kategori
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

            data = {
                "slug": make_slug(article["url"]),
                "title": article["title"],
                "description": article["description"][:300],
                "summary": summary,
                "content": content,                  # ← ISI LENGKAP
                "image_url": article.get("image") or "",
                "source_name": article.get("source", "Media"),
                "original_url": article["url"],
                "published_at": article.get("published_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "category": category,
            }

            insert_res = requests.post(
                f"{SUPABASE_URL}/rest/v1/news_archive",
                json=data, headers=headers_supabase, timeout=6,
            )

            # Fallback: kalau kolom `content` tidak ada, retry tanpa content
            if insert_res.status_code == 400 and "content" in insert_res.text.lower():
                print(f"[Supabase] kolom 'content' tidak ada, retry tanpa content")
                del data["content"]
                insert_res = requests.post(
                    f"{SUPABASE_URL}/rest/v1/news_archive",
                    json=data, headers=headers_supabase, timeout=6,
                )

            if insert_res.status_code in (200, 201):
                try:
                    body = insert_res.json() if insert_res.text else []
                except Exception:
                    body = []
                if isinstance(body, list) and len(body) > 0:
                    inserted_count += 1
            else:
                insert_errors.append(f"HTTP {insert_res.status_code}: {insert_res.text[:150]}")
        except Exception as e:
            insert_errors.append(str(e))

    return {
        "status": "success" if inserted_count > 0 else ("partial" if insert_errors else "no_new"),
        "source": "rss",
        "inserted": inserted_count,
        "checked": len(articles),
        "new_found": len(new_articles),
        "errors": insert_errors[:3] if insert_errors else [],
        "message": f"{inserted_count} berita baru disimpan." if inserted_count else "Tidak ada berita baru.",
    }


# ==========================================
# 🆕 AMBIL ISI LENGKAP DARI SUMBER (via Jina Reader)
# ==========================================
@app.get("/api/news/content")
def get_full_article(url: str):
    """
    Ambil isi artikel lengkap dari URL sumber via Jina AI Reader.
    Frontend memanggil ini saat user klik "Muat Isi Lengkap".
    """
    if not url:
        raise HTTPException(status_code=400, detail="Parameter 'url' wajib diisi.")

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL tidak valid.")

    try:
        jina_url = f"https://r.jina.ai/{url}"
        r = requests.get(jina_url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EconomicInsightBot/1.0)",
            "Accept": "text/plain",
        })

        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Jina Reader HTTP {r.status_code}")

        text = (r.text or "").strip()

        # Jina format: "Title: ...\n\nURL Source: ...\n\nMarkdown Content:\n\n<isi>"
        if "Markdown Content:" in text:
            text = text.split("Markdown Content:", 1)[1].strip()

        # Bersihkan markdown image/link sintaks
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if len(text) < 100:
            raise HTTPException(status_code=502, detail="Konten artikel terlalu pendek / gagal diekstrak.")

        max_len = 15000
        if len(text) > max_len:
            text = text[:max_len] + "\n\n[... artikel dipotong karena batas panjang ...]"

        return {
            "status": "success",
            "url": url,
            "content": text,
            "length": len(text),
        }

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout saat mengambil artikel.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal: {type(e).__name__}: {str(e)[:200]}")


# ==========================================
# PREVIEW SHARE
# ==========================================
@app.get("/api/preview")
def preview_link(id: str = ""):
    if not id:
        return HTMLResponse(content="<h1>Link Tidak Valid</h1>", status_code=400)

    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/share_links?id=eq.{id}", headers=headers, timeout=5)
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
<html lang="id"><head>
<meta charset="UTF-8"><title>{title}</title>
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
</head><body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; background-color: #f8fafc;">
<div style="text-align:center;"><h3>Membuka berita...</h3><p><a href="{redirect_url}">Klik di sini jika tidak dialihkan</a></p></div>
</body></html>"""
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)


@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
