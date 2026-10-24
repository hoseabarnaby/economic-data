from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil API Key dari Environment Variable Vercel
BPS_API_KEY = os.getenv("BPS_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ==========================================
# ENDPOINT 1: AMBIL DATA BPS (Inflasi)
# ==========================================
@app.get("/api/inflasi")
def get_inflasi():
    if not BPS_API_KEY:
        raise HTTPException(status_code=500, detail="API Key BPS belum diatur di Vercel.")
    
    # (Biarkan kode BPS Anda yang sebelumnya di sini, atau gunakan versi fallback ini)
    try:
        # Simulasi (Ganti dengan kode fetch BPS asli Anda jika sudah berjalan)
        return {"nilai": 2.56, "tahun": 2026}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# ENDPOINT 2: CHAT DEEPSEEK AI (Floating Window)
# ==========================================
class ChatRequest(BaseModel):
    message: str
    context: str

@app.post("/api/chat")
def chat_with_deepseek(req: ChatRequest):
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API Key belum diatur di Vercel.")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    # Prompt Sistem (Menyuruh AI menjadi analis ekonomi dan membaca data dari frontend)
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

# Endpoint Health Check
@app.get("/api")
def read_root():
    return {"status": "Backend Vercel Aktif"}
