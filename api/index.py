from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import urlencode
import requests
import os
import base64
import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# DATABASE BARU KAMU
SUPABASE_URL = 'https://gwkqmhsmlmmzcmqcqpft.supabase.co'
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd3a3FtaHNtbG1temNtcWNxcGZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwMDYwMzcsImV4cCI6MjEwODU4MjAzN30.AXKbMO3dQw8mEWbmDsSVxSMMjthBxyJWfZUpC8_afWI'

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
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    system_prompt = f"Anda adalah AI Economic Insight, asisten analis keuangan cerdas.\nData konteks: {req.context}"
    payload = {"model": "deepseek-chat", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": req.message}], "stream": False}
    
    try:
        response = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return {"reply": response.json()['choices'][0]['message']['content']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal: {str(e)}")

@app.get("/api/news/sync")
def sync_news():
    if not DEEPSEEK_API_KEY:
        return {"status": "error", "message": "DEEPSEEK_API_KEY belum diset di Vercel."}

    headers_supabase = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    try:
        # 1. Ambil 20 berita terbaru dari API
        r = requests.get("https://freenewsapi.ai/v1/search?lang=id&q=ekonomi+indonesia&size=20", timeout=5)
        articles = r.json().get('results', [])
        
        if not articles:
            return {"status": "success", "message": "Tidak ada berita dari API."}

        processed_count = 0
        
        # 2. Looping mencari 1 berita yang BELUM ada di database
        for article in articles:
            url = article.get('url')
            
            # Cek duplikat di Supabase
            check_url = f"{SUPABASE_URL}/rest/v1/news_archive?original_url=eq.{url}"
            check_res = requests.get(check_url, headers=headers_supabase)
            
            if check_res.status_code == 200 and len(check_res.json()) > 0:
                continue # Kalau sudah ada, skip dan cek berita berikutnya

            # --- KETEMU BERITA BARU! ---
            
            # 3. Minta ringkasan ke DeepSeek
            content = (article.get('content') or article.get('description') or '')[:3000]
            prompt = f"Ringkas berita ini dalam 2 paragraf singkat (maks 150 kata).\nJudul: {article.get('title')}\nKonten: {content}"
            ai_payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300}
            
            try:
                ai_res = requests.post("https://api.deepseek.com/chat/completions", json=ai_payload, headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, timeout=8)
                summary = ai_res.json()['choices'][0]['message']['content']
            except Exception:
                summary = content # Fallback ke konten asli jika AI gagal

            # 4. Deteksi Kategori
            text_lower = (article.get('title', '') + " " + content).lower()
            category = 'umum'
            if any(k in text_lower for k in ['pangan', 'beras', 'cabai', 'daging', 'telur', 'gula']): category = 'pangan'
            elif any(k in text_lower for k in ['saham', 'ihsg', 'rupiah', 'kurs', 'bank', 'investasi']): category = 'keuangan'
            elif any(k in text_lower for k in ['bbm', 'minyak', 'gas', 'listrik', 'energi']): category = 'energi'
            elif any(k in text_lower for k in ['pajak', 'apbn', 'fiskal', 'bi rate', 'inflasi']): category = 'kebijakan'

            slug = base64.urlsafe_b64encode(url.encode()).decode()[:40]

            # 5. Simpan ke Supabase
            data = {
                "slug": slug,
                "title": article.get('title', 'Tanpa Judul'),
                "description": content[:200],
                "summary": summary,
                "image_url": article.get('image') or article.get('thumbnail') or '',
                "source_name": article.get('source', 'Media'),
                "original_url": url,
                "published_at": article.get('published_at') or datetime.datetime.now().isoformat(),
                "category": category
            }
            
            insert_res = requests.post(f"{SUPABASE_URL}/rest/v1/news_archive", json=data, headers=headers_supabase)
            
            if insert_res.status_code in [200, 201]:
                processed_count += 1
                break # BERHENTI SETELAH 1 BERITA BARU DISIMPAN (Anti Timeout)

        if processed_count == 0:
            return {"status": "success", "message": "Semua 20 berita terbaru sudah ada di database. Coba lagi nanti."}

        return {"status": "success", "message": "1 berita baru berhasil disimpan!"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/preview")
def preview_link(id: str = ""):
    if not id: 
        return HTMLResponse(content="<h1>Link Tidak Valid</h1>", status_code=400)
        
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/share_links?id=eq.{id}", headers=headers)
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

@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
