from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import unquote
import requests
import os

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

@app.get("/api/preview")
def preview_link(id: str = ""):
    if not id:
        return HTMLResponse(content="<h1>Link Tidak Valid</h1>", status_code=400)

    # Ambil data dari Supabase berdasarkan ID
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

        if img.startswith('http://'):
            img = img.replace('http://', 'https://')

        redirect_url = f"https://economic-data-lake.vercel.app/?news_url={original_url}"

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
