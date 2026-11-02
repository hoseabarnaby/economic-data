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

# ==========================================
# KONFIGURASI SUPABASE (dari ENV Vercel, dengan fallback)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", 'https://gwkqmhsmlmmzcmqcqpft.supabase.co')
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd3a3FtaHNtbG1temNtcWNxcGZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwMDYwMzcsImV4cCI6MjEwODU4MjAzN30.AXKbMO3dQw8mEWbmDsSVxSMMjthBxyJWfZUpC8_afWI'
)

# RSS fallback (Kompas dihapus karena 404)
RSS_FEEDS = [
    {"url": "https://www.antaranews.com/rss/ekonomi.xml", "source": "Antara News"},
    {"url": "https://finance.detik.com/rss",               "source": "Detik Finance"},
    {"url": "https://www.cnbcindonesia.com/rss",          "source": "CNBC Indonesia"},
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EconomicInsightBot/1.0)",
    "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
}


# ==========================================
# ✅ HELPER: SLUG UNIK (SHA-256)
# ==========================================
def make_slug(url: str) -> str:
    """
    Generate slug unik dari URL menggunakan SHA-256.
    Jauh lebih aman daripada base64[:40] yang rawan bentrok.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


# ==========================================
# ✅ ENDPOINT CONFIG (dibutuhkan index.html)
# ==========================================
@app.get("/api/config")
def get_config():
    return {
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": SUPABASE_ANON_KEY,
    }


# ==========================================
# ✅ ENDPOINT INFLASI
# ==========================================
@app.get("/api/inflasi")
def get_inflasi():
    return {"nilai": 2.56, "tahun": 2026}


# ==========================================
# ✅ ENDPOINT AI CHAT (DeepSeek)
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
# HELPER: FETCH DARI FREENEWSAPI (PRIMARY)
# ==========================================
def fetch_from_freenewsapi():
    try:
        url = "https://freenewsapi.ai/v1/search?lang=id&q=ekonomi+indonesia&size=20"
        r = requests.get(url, timeout=15, headers=COMMON_HEADERS)

        if r.status_code != 200:
            return [], f"freenewsapi HTTP {r.status_code}"

        try:
            data = r.json()
        except ValueError:
            return [], f"freenewsapi non-JSON (kemungkinan down): {r.text[:150]}"

        results = data.get('results', [])
        if not results:
            return [], f"freenewsapi 0 results. Keys: {list(data.keys())[:5]}"

        articles = []
        for a in results:
            u = a.get('url')
            if not u:
                continue
            articles.append({
                "title": a.get('title', 'Tanpa Judul'),
                "url": u,
                "content": (a.get('content') or a.get('description') or '')[:2500],
                "description": (a.get('description') or a.get('content') or '')[:500],
                "image": a.get('image') or a.get('thumbnail') or '',
                "source": a.get('source', 'Media'),
                "published_at": a.get('published_at') or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        return articles, None

    except requests.exceptions.Timeout:
        return [], "freenewsapi TIMEOUT (>15s)"
    except requests.exceptions.ConnectionError:
        return [], "freenewsapi CONNECTION ERROR (DNS / network)"
    except Exception as e:
        return [], f"freenewsapi {type(e).__name__}: {str(e)[:120]}"


# ==========================================
# HELPER: FETCH DARI RSS (FALLBACK)
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
                except Exception:
                    continue
        except Exception as e:
            print(f"[RSS] {feed['source']} error: {e}")
            continue

    return articles


# ==========================================
# ✅ ENDPOINT SYNC BERITA (HYBRID + UPSERT)
# ==========================================
@app.get("/api/news/sync")
def sync_news():
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY belum diset di Vercel.")

    # ⚠️ PENTING: resolution=ignore-duplicates mencegah error 409 saat slug/URL bentrok
    headers_supabase = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation",
    }

    # ─── 1. AMBIL BERITA (primary → fallback) ──────────────
    source_used = None
    errors_log = []

    articles, primary_err = fetch_from_freenewsapi()
    if articles:
        source_used = "freenewsapi"
    else:
        errors_log.append(primary_err)
        print(f"[Primary] gagal: {primary_err} → fallback ke RSS")
        articles = fetch_from_rss()
        if articles:
            source_used = "rss"

    if not articles:
        raise HTTPException(
            status_code=502,
            detail={"message": "Semua sumber berita gagal.", "errors": errors_log},
        )

    # ─── 2. BATCH CHECK DUPLIKAT (by URL) ──────────────────
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
        else:
            print(f"[Supabase] batch check HTTP {check_res.status_code}: {check_res.text[:200]}")
    except Exception as e:
        print(f"[Supabase] batch check error: {e}")

    new_articles = [a for a in articles if a["url"] not in existing_urls]

    if not new_articles:
        return {
            "status": "success",
            "source": source_used,
            "inserted": 0,
            "ignored": 0,
            "checked": len(articles),
            "message": f"Semua {len(articles)} artikel ({source_used}) sudah ada di database.",
        }

    # ─── 3. PROSES MAKS 3 ARTIKEL BARU (anti timeout) ──────
    inserted_count = 0
    ignored_count = 0
    insert_errors = []

    for article in new_articles[:3]:
        try:
            content = (article.get("content") or article.get("description") or "")[:2500]

            # Ringkas dengan DeepSeek (fallback ke konten asli)
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
                        timeout=10,
                    )
                    ai_res.raise_for_status()
                    summary = ai_res.json()["choices"][0]["message"]["content"]
                except Exception as ai_err:
                    print(f"[AI] fallback ke konten asli: {ai_err}")

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

            # ✅ SLUG UNIK pakai SHA-256
            slug = make_slug(article["url"])

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
                json=data, headers=headers_supabase, timeout=6,
            )

            if insert_res.status_code in (200, 201):
                # Deteksi apakah benar-benar inserted atau ignored
                # (ignore-duplicates + return=representation → array kosong kalau ignored)
                try:
                    body = insert_res.json() if insert_res.text else []
                except Exception:
                    body = []

                if isinstance(body, list) and len(body) > 0:
                    inserted_count += 1
                else:
                    ignored_count += 1
            else:
                insert_errors.append(
                    f"{article['title'][:40]}... -> HTTP {insert_res.status_code}: {insert_res.text[:120]}"
                )
        except Exception as e:
            insert_errors.append(str(e))

    # ─── 4. RETURN INFORMATIF ─────────────────────────────
    return {
        "status": "success" if inserted_count > 0 else ("partial" if insert_errors else "no_new"),
        "source": source_used,
        "inserted": inserted_count,
        "ignored": ignored_count,
        "checked": len(articles),
        "new_found": len(new_articles),
        "fallback_used": source_used == "rss",
        "primary_error": errors_log[0] if errors_log else None,
        "errors": insert_errors[:3] if insert_errors else [],
        "message": (
            f"{inserted_count} berita baru disimpan dari {source_used}."
            + (f" ({ignored_count} dilewati karena duplikat)" if ignored_count else "")
            if inserted_count
            else ("Semua berita duplikat, tidak ada yang baru." if ignored_count else "Tidak ada berita yang berhasil disimpan.")
        ),
    }


# ==========================================
# 🆕 ENDPOINT DEBUG NEWS
# ==========================================
@app.get("/api/debug/news")
def debug_news():
    result = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "supabase_config": {
            "url_loaded": bool(SUPABASE_URL),
            "key_loaded": bool(SUPABASE_ANON_KEY),
        },
        "freenewsapi": {},
        "rss": {},
    }

    try:
        r = requests.get(
            "https://freenewsapi.ai/v1/search?lang=id&q=ekonomi+indonesia&size=5",
            timeout=15, headers=COMMON_HEADERS,
        )
        result["freenewsapi"]["status_code"] = r.status_code
        result["freenewsapi"]["content_type"] = r.headers.get("content-type", "?")
        result["freenewsapi"]["body_preview"] = r.text[:300]
        try:
            j = r.json()
            result["freenewsapi"]["is_json"] = True
            result["freenewsapi"]["keys"] = list(j.keys())[:10]
            result["freenewsapi"]["results_count"] = len(j.get("results", []))
        except Exception:
            result["freenewsapi"]["is_json"] = False
    except Exception as e:
        result["freenewsapi"]["error"] = f"{type(e).__name__}: {str(e)[:200]}"

    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed["url"], timeout=5, headers=COMMON_HEADERS)
            result["rss"][feed["source"]] = {
                "status_code": r.status_code,
                "size_bytes": len(r.content),
            }
        except Exception as e:
            result["rss"][feed["source"]] = {"error": str(e)[:100]}

    return result


# ==========================================
# 🆕 ENDPOINT DEBUG SUPABASE
# ==========================================
@app.get("/api/debug/supabase")
def debug_supabase():
    """Test apakah anon key bisa baca & insert ke news_archive."""
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    result = {"url": SUPABASE_URL, "read": {}, "insert_test": {}}

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_archive?select=slug,title,published_at&limit=3&order=published_at.desc",
            headers=headers, timeout=8,
        )
        result["read"]["status_code"] = r.status_code
        result["read"]["body"] = r.text[:500]
        if r.status_code == 200:
            data = r.json()
            result["read"]["row_count_in_sample"] = len(data)
            result["read"]["has_data"] = len(data) > 0
            if data:
                result["read"]["first_row_preview"] = {
                    "slug": data[0].get("slug"),
                    "title": (data[0].get("title") or "")[:60],
                    "published_at": data[0].get("published_at"),
                }
    except Exception as e:
        result["read"]["error"] = str(e)

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/news_archive?select=slug",
            headers={**headers, "Prefer": "count=exact", "Range": "0-0"},
            timeout=8,
        )
        result["read"]["total_count_header"] = r.headers.get("content-range", "?")
    except Exception as e:
        result["read"]["count_error"] = str(e)

    # Test insert dengan slug SHA-256 (pasti unik)
    test_url = f"https://debug.test/{datetime.datetime.now().timestamp()}"
    test_slug = make_slug(test_url)
    test_data = {
        "slug": test_slug,
        "title": "TEST DEBUG - akan dihapus otomatis",
        "description": "Test",
        "summary": "Test",
        "image_url": "",
        "source_name": "Debug",
        "original_url": test_url,
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "category": "umum",
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/news_archive",
            json=test_data,
            headers={**headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
            timeout=8,
        )
        result["insert_test"]["status_code"] = r.status_code
        result["insert_test"]["body"] = r.text[:400]
        result["insert_test"]["success"] = r.status_code in (200, 201)

        if r.status_code in (200, 201):
            requests.delete(
                f"{SUPABASE_URL}/rest/v1/news_archive?slug=eq.{test_slug}",
                headers=headers, timeout=5,
            )
            result["insert_test"]["cleaned_up"] = True
    except Exception as e:
        result["insert_test"]["error"] = str(e)

    return result


# ==========================================
# ✅ ENDPOINT PREVIEW SHARE
# ==========================================
@app.get("/api/preview")
def preview_link(id: str = ""):
    if not id:
        return HTMLResponse(content="<h1>Link Tidak Valid</h1>", status_code=400)

    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/share_links?id=eq.{id}",
            headers=headers, timeout=5,
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
# ✅ ENDPOINT ROOT
# ==========================================
@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
