from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import os

IP = requests.get("https://api.ipify.org").text

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"""
        <html>
        <body>
        <h1>80억 프로젝트</h1>
        <p>현재 Render IP : {IP}</p>
        </body>
        </html>
        """
        self.send_response(200)
        self.end_headers()
        self.wfile.write(html.encode())

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
