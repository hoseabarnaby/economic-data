from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Ambil parameter dari URL
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        # Nilai default jika parameter kosong
        title = query.get('title', ['Economic Insight - Global Economic Intelligence'])[0]
        desc = query.get('desc', ['Pantau berita ekonomi, kurs, dan kebijakan terbaru secara real-time.'])[0]
        img = query.get('img', ['https://placehold.co/1200x630/2563eb/ffffff/png?text=Economic+Insight%0A%0ABerita+Ekonomi+Terbaru&font=Montserrat'])[0]
        url = query.get('url', [''])[0]

        # URL tujuan redirect (sesuaikan jika domain Anda berbeda)
        redirect_url = f"https://economic-data-lake.vercel.app/?news_url={url}"

        # 2. Buat kode HTML dengan Meta Tag dinamis
        html = f"""
        <!DOCTYPE html>
        <html lang="id">
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            
            <!-- Open Graph / Facebook / WhatsApp -->
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
            
            <!-- Redirect otomatis ke halaman utama -->
            <meta http-equiv="refresh" content="0; url={redirect_url}" />
        </head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; text-align: center; padding: 20px;">
            <div>
                <h3>Mengalihkan ke berita...</h3>
                <p><a href="{redirect_url}">Klik di sini jika tidak dialihkan secara otomatis</a>.</p>
            </div>
            <script>
                window.location.href = "{redirect_url}";
            </script>
        </body>
        </html>
        """

        # 3. Kirim respons HTML
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
