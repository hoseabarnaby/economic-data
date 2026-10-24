from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os

app = FastAPI()

# Izinkan akses dari frontend Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil API Key dari Vercel Environment Variables
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BPS_API_KEY = os.getenv("BPS_API_KEY") # Opsional jika pakai BPS

# ==========================================
# 1. ENDPOINT UNTUK INFLASI
# ==========================================
@app.get("/inflasi")
def get_inflasi():
    # Ini adalah data simulasi. Ganti dengan data BPS asli jika sudah siap.
    return {"nilai": 2.56, "tahun": 2026}

# ==========================================
# 2. ENDPOINT UNTUK CHAT DEEPSEEK
# ==========================================
class ChatRequest(BaseModel):
    message: str
    context: str

@app.post("/chat")
def chat_with_deepseek(req: ChatRequest):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="API Key DeepSeek belum diatur di Vercel.")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""Anda adalah "Economic Insight AI", asisten analis ekonomi profesional. 
Data real-time saat ini:
{req.context}

Jawablah pertanyaan pengguna dengan cerdas, ringkas, dan berikan analisis berdasarkan data di atas. Jika ditanya di luar topik ekonomi, jawab dengan sopan bahwa Anda hanya asisten ekonomi."""

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
        raise HTTPException(status_code=500, detail=f"Gagal memanggil DeepSeek: {str(e)}")

# Endpoint root untuk tes
@app.get("/")
def read_root():
    return {"status": "Backend Python Vercel Aktif"}
