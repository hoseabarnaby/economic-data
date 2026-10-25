from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Ambil parameter dari URL
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        # 2. Nilai default (jika parameter tidak terbaca)
        title = query.get('title', ['Economic Insight'])[0]
        desc = query.get('desc', ['Baca berita ekonomi terbaru di Economic Insight.'])[0]
        img = query.get('img', ['https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight'])[0]
        url = query.get('url', ['https://economic-data-lake.vercel.app/'])[0]

        # 3. URL tujuan redirect
        redirect_url = f"https://economic-data-lake.vercel.app/?news_url={url}"

        # 4. Buat kode HTML (TANPA JavaScript redirect agar tidak kena blokir)
        html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    
    <!-- Open Graph (WhatsApp/FB) -->
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:image" content="{img}" />
    <meta property="og:url" content="{redirect_url}" />

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{desc}" />
    <meta name="twitter:image" content="{img}" />
    
    <!-- Redirect Instan via HTTP Header (Lebih Stabil) -->
    <meta http-equiv="refresh" content="0; url={redirect_url}" />
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; text-align:center; padding: 20px; background-color: #f8fafc;">
    <div>
        <h2 style="color: #1e293b;">Mengalihkan ke berita...</h2>
        <p style="color: #64748b; margin-bottom: 20px;">Jika tidak dialihkan secara otomatis, klik link di bawah ini:</p>
        <a href="{redirect_url}" style="background-color: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: bold;">Buka Berita</a>
    </div>
</body>
</html>"""

        # 5. Kirim respons HTML
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
