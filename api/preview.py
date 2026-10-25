from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # 1. Ambil parameter
            parsed_path = urlparse(self.path)
            query = parse_qs(parsed_path.query)

            title = html.escape(query.get('title', ['Economic Insight'])[0])
            desc = html.escape(query.get('desc', ['Pantau berita ekonomi terbaru.'])[0])
            url = query.get('url', ['https://economic-data-lake.vercel.app/'])[0]
            
            # 2. Ambil gambar dan paksa pakai HTTPS (WhatsApp menolak HTTP)
            img = query.get('img', ['https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight'])[0]
            if img.startswith('http://'):
                img = img.replace('http://', 'https://')
            
            # 3. URL Redirect
            redirect_url = f"https://economic-data-lake.vercel.app/?news_url={url}"

            # 4. HTML Preview
            html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    
    <!-- Meta Tag untuk WhatsApp / Facebook -->
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:image" content="{img}" />
    <meta property="og:url" content="{redirect_url}" />

    <!-- Meta Tag untuk Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{desc}" />
    <meta name="twitter:image" content="{img}" />
    
    <!-- Redirect Instan -->
    <meta http-equiv="refresh" content="0; url={redirect_url}" />
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; text-align:center;">
    <div>
        <p>Mengalihkan...</p>
        <a href="{redirect_url}">Klik jika tidak dialihkan</a>
    </div>
</body>
</html>"""

            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
            
        except Exception as e:
            # Jika error, tampilkan pesan error agar tidak "blank hitam"
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))
