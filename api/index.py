from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import unquote, urlencode
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
    except requests.exceptions.HTTPError as errh:
        raise HTTPException(status_code=response.status_code, detail=f"DeepSeek Error: {response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memanggil DeepSeek: {str(e)}")

@app.get("/api/preview")
def preview_link(title: str = "Economic Insight", desc: str = "Baca berita ekonomi terbaru.", img: str = "", url: str = ""):
    title = unquote(title).replace('"', '&quot;')
    desc = unquote(desc).replace('"', '&quot;')
    img = unquote(img)
    url = unquote(url)

    if img.startswith('http://'):
        img = img.replace('http://', 'https://')
        
    if not img or img.startswith('data:image'):
        img = 'https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight'

    my_website = "https://economic-data-lake.vercel.app/"
    
    # PERBAIKAN: Kirim semua data (title, desc, img) ke URL redirect
    query_params = urlencode({
        'news_url': url,
        'title': title,
        'desc': desc,
        'img': img
    })
    
    redirect_url = f"{my_website}?{query_params}"

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
        <h3 style="color: #1e293b;">Membuka berita di Economic Insight...</h3>
        <p><a href="{redirect_url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Klik di sini jika tidak dialihkan secara otomatis</a></p>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html_content, status_code=200)

@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
