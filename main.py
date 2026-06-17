from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"""
        <html>
        <body>
        <h1>80억 프로젝트</h1>
        <p>{datetime.now()}</p>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

port = int(os.environ.get("PORT", 10000))

print(f"서버 시작: {port}")

server = HTTPServer(("0.0.0.0", port), Handler)
server.serve_forever()
