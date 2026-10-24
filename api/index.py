# api/index.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI()

# Izinkan frontend (Vercel) untuk mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Ganti dengan domain Vercel Anda saat produksi
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil API Key BPS dari environment variable (jangan di-hardcode)
BPS_API_KEY = os.getenv("BPS_API_KEY")

@app.get("/api/inflasi")
def get_inflasi():
    if not BPS_API_KEY:
        raise HTTPException(status_code=500, detail="API Key BPS belum diatur di Vercel.")

    # Contoh endpoint BPS untuk data Inflasi (ID variabel 1921)
    # Anda perlu menyesuaikan parameter ini dengan data BPS yang ingin diambil
    url = f"https://webapi.bps.go.id/v1/api/interoperabilitas/datasource/simdasi/wilayah/0000/id/1921/th/126/key/{BPS_API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Akan error jika status bukan 2xx
        data_bps = response.json()

        # --- LOGIKA PARSING DATA BPS ---
        # Struktur JSON BPS sangat berlapis. Anda perlu menyesuaikan bagian ini.
        # Contoh sederhana: ambil nilai dari path tertentu.
        # if data_bps and 'data' in data_bps:
        #     nilai_inflasi = data_bps['data'][0]['value']
        #     return {"indikator": "Inflasi YoY", "nilai": nilai_inflasi, "sumber": "BPS"}
        
        # Untuk sementara, kita kembalikan data mentah agar Anda bisa melihat strukturnya
        return {"message": "Berhasil mengambil data dari BPS", "raw_data": data_bps}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil data dari BPS: {e}")

# Endpoint root untuk health check
@app.get("/api")
def read_root():
    return {"status": "Backend Python di Vercel aktif"}