from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.parse

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Ambil parameter dari URL (title, desc, img, url)
        query = parse_qs(urlparse(self.path).query)
        
        title = query.get('title', ['Economic Insight'])[0]
        desc = query.get('desc', ['Baca berita ekonomi terbaru.'])[0]
        img = query.get('img', ['https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight'])[0]
        target_url = query.get('url', ['https://economic-data-lake.vercel.app/'])[0]
        
        # Decode URL-encoded text (misal %20 jadi spasi)
        title = urllib.parse.unquote(title)
        desc = urllib.parse.unquote(desc)
        img = urllib.parse.unquote(img)
        
        # Pastikan gambar pakai HTTPS
        if img.startswith('http://'):
            img = img.replace('http://', 'https://')
        
        # 2. Rakit HTML dengan Meta Tag Dinamis (Persis seperti di file teks)
        html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    
    <!-- Open Graph untuk WhatsApp / Facebook / Telegram -->
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:image" content="{img}" />
    <meta property="og:url" content="{target_url}" />
    <meta property="og:type" content="article" />

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">
    <meta name="twitter:image" content="{img}">
    
    <!-- Redirect ke website asli setelah dibaca bot -->
    <meta http-equiv="refresh" content="0; url={target_url}" />
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; text-align:center; padding: 20px; background-color: #f8fafc;">
    <div>
        <h3 style="color: #1e293b;">Mengalihkan ke berita...</h3>
        <p><a href="{target_url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Klik di sini jika tidak dialihkan secara otomatis</a></p>
    </div>
</body>
</html>"""

        # 3. Kirim ke browser/bot
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
