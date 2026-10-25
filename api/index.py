from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from urllib.parse import unquote
import requests
import os

app = FastAPI()

# Izinkan frontend Vercel untuk mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil API Key dari Environment Variable Vercel
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ==========================================
# 1. ENDPOINT UNTUK INFLASI (Dipanggil oleh /api/inflasi)
# ==========================================
@app.get("/api/inflasi")
def get_inflasi():
    # Data simulasi. Bisa diganti dengan data BPS asli jika sudah siap.
    return {"nilai": 2.56, "tahun": 2026}

# ==========================================
# 2. ENDPOINT UNTUK CHAT DEEPSEEK (Dipanggil oleh /api/chat)
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

# ==========================================
# 3. ENDPOINT UNTUK SHARE PREVIEW / OG TAGS (Dipanggil oleh /api/preview)
# ==========================================
@app.get("/api/preview")
def preview_link(title: str = "Economic Insight", desc: str = "Baca berita ekonomi terbaru.", img: str = "", url: str = "https://economic-data-lake.vercel.app/"):
    # Decode URL (mengubah %20 menjadi spasi, dll)
    title = unquote(title).replace('"', '&quot;')
    desc = unquote(desc).replace('"', '&quot;')
    img = unquote(img)
    url = unquote(url)

    # Paksa HTTPS untuk gambar (WhatsApp menolak HTTP)
    if img.startswith('http://'):
        img = img.replace('http://', 'https://')
        
    # Jika gambar kosong atau berupa data URI, gunakan gambar default
    if not img or img.startswith('data:image'):
        img = 'https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight'

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    
    <!-- Open Graph Tags untuk WhatsApp / Facebook / Telegram -->
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:image" content="{img}" />
    <meta property="og:url" content="{url}" />
    <meta property="og:type" content="article" />

    <!-- Twitter Cards -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">
    <meta name="twitter:image" content="{img}">
    
    <!-- Redirect ke Website Asli -->
    <meta http-equiv="refresh" content="0; url={url}" />
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; background-color: #f8fafc;">
    <div style="text-align:center;">
        <h3 style="color: #1e293b;">Mengalihkan ke berita...</h3>
        <p><a href="{url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Klik di sini jika tidak dialihkan secara otomatis</a></p>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html_content, status_code=200)

# Endpoint Health Check (Untuk memastikan server hidup)
@app.get("/api")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
