from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import unquote, urlencode
import requests
import os
import base64
import datetime
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SUPABASE_URL = 'https://nqoohtklfqhcpfcllsok.supabase.co'
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5xb29odGtsZnFoY3BmY2xsc29rIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI4MDYwODksImV4cCI6MjEwODM4MjA4OX0.xV7YhW2GS1KBwgAio-NRQxFfyIJ_aG8wVRuhPY5efrQ'

@app.get("/api/inflasi")
def get_inflasi():
    return {"nilai": 2.56, "tahun": 2026}

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

    system_prompt = f"""Anda adalah "AI Economic Insight", asisten analis keuangan dan ekonomi yang cerdas, canggih, dan membantu.
    
Data pasar real-time saat ini:
{req.context}

Panduan Anda:
1. Jawablah pertanyaan pengguna dengan gaya bahasa profesional namun mudah dipahami.
2. Anda BEBAS menjawab pertanyaan seputar makroekonomi, pasar saham, cryptocurrency (seperti Bitcoin, Ethereum), komoditas, kurs, dan topik keuangan lainnya.
3. JANGAN menolak pertanyaan pengguna. Jika pertanyaannya di luar data konteks yang diberikan, gunakan pengetahuan internal Anda yang luas untuk menjawab.
4. Jika pengguna meminta prediksi (seperti harga Bitcoin), berikan analisis objektif berdasarkan tren pasar, sentimen, dan berita terkini, serta sertakan disclaimer singkat bahwa itu bukan saran investasi mutlak."""

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
        data = response.json()
        reply = data['choices'][0]['message']['content']
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal: {str(e)}")

# ==========================================
# ENDPOINT BARU: SYNC NEWS & RINGKASAN AI
# ==========================================
@app.get("/api/news/sync")
def sync_news():
    if not DEEPSEEK_API_KEY:
        return {"status": "error", "message": "DEEPSEEK_API_KEY belum diset."}

    headers_supabase = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates" # Abaikan jika URL sudah ada
    }

    try:
        # 1. Ambil berita dari Freenewsapi
        queries = ['ekonomi indonesia', 'kebijakan ekonomi', 'pasar saham indonesia']
        raw_results = []
        
        for q in queries:
            try:
                r = requests.get(f"https://freenewsapi.ai/v1/search?lang=id&q={q}&size=5", timeout=5)
                if r.status_code == 200:
                    raw_results.extend(r.json().get('results', []))
            except:
                pass

        # Hapus duplikat berdasarkan URL
        unique_articles = list({v['url']: v for v in raw_results}.values())
        if not unique_articles:
            return {"status": "success", "message": "Tidak ada berita baru."}

        processed_count = 0
        
        # 2. Loop dan proses (Maksimal 3 agar tidak timeout Vercel)
        for article in unique_articles:
            if processed_count >= 3:
                break
                
            url = article.get('url')
            title = article.get('title', '')
            content = article.get('content') or article.get('description') or ''
            image = article.get('image') or article.get('thumbnail') or ''
            source = article.get('source', 'Media')
            published_at = article.get('published_at', datetime.datetime.now().isoformat())
            
            # Cek dulu apakah sudah ada di DB
            check_res = requests.get(f"{SUPABASE_URL}/rest/v1/news_archive?original_url=eq.{url}&select=id", headers=headers_supabase)
            if check_res.status_code == 200 and len(check_res.json()) > 0:
                continue # Skip jika sudah ada

            # 3. Minta ringkasan ke DeepSeek
            prompt = f"Ringkas berita ekonomi berikut dalam 2-3 paragraf (250-300 kata) Bahasa Indonesia. Fokus pada fakta utama, dampak ekonomi, dan konteks. Tanpa bullet point.\n\nJudul: {title}\nKonten: {content}"
            
            ai_payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Anda jurnalis ekonomi senior."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 800
            }
            
            try:
                ai_res = requests.post("https://api.deepseek.com/chat/completions", json=ai_payload, headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, timeout=20)
                summary = ai_res.json()['choices'][0]['message']['content']
            except:
                summary = content # Fallback ke konten asli jika AI gagal

            # 4. Deteksi Kategori
            text_lower = (title + " " + content).lower()
            category = 'umum'
            if any(k in text_lower for k in ['pangan', 'beras', 'cabai', 'daging', 'telur', 'gula']): category = 'pangan'
            elif any(k in text_lower for k in ['saham', 'ihsg', 'rupiah', 'kurs', 'bank', 'investasi']): category = 'keuangan'
            elif any(k in text_lower for k in ['bbm', 'minyak', 'gas', 'listrik', 'energi']): category = 'energi'
            elif any(k in text_lower for k in ['pajak', 'apbn', 'fiskal', 'bi rate', 'inflasi']): category = 'kebijakan'

            slug = base64.urlsafe_b64encode(url.encode()).decode()[:40]

            # 5. Simpan ke Supabase
            data = {
                "slug": slug,
                "title": title,
                "description": content[:300],
                "summary": summary,
                "image_url": image,
                "source_name": source,
                "original_url": url,
                "published_at": published_at,
                "category": category
            }
            
            insert_res = requests.post(f"{SUPABASE_URL}/rest/v1/news_archive", json=data, headers=headers_supabase)
            if insert_res.status_code in [201, 200]:
                processed_count += 1

            time.sleep(1) # Jeda antar request DeepSeek

        return {"status": "success", "inserted": processed_count}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# PREVIEW LINK (TETAP SEPERTI SEBELUMNYA)
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
        res = requests.get(f"{SUPABASE_URL}/rest/v1/share_links?id=eq.{id}", headers=headers)
        data = res.json()

        if not data or len(data) == 0:
            return HTMLResponse(content="<h1>Berita tidak ditemukan atau link kadaluarsa</h1>", status_code=404)

        news = data[0]
        title = news.get('title', 'Economic Insight')
        desc = news.get('description', 'Baca berita ekonomi terbaru.')
        img = news.get('image_url', '')
        original_url = news.get('original_url', 'https://economic-data-lake.vercel.app/')

        if img and img.startswith('http://'):
            img = img.replace('http://', 'https://')

        query_params = urlencode({
            'news_url': original_url,
            'title': title,
            'desc': desc,
            'img': img
        })
        
        redirect_url = f"https://economic-data-lake.vercel.app/?{query_params}"

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

@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
