from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html = f"""
        <html>
        <head>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="30">
        <title>80억 프로젝트</title>
        </head>
        <body style="font-family:sans-serif;padding:20px;">
            <h1>🚀 80억 프로젝트</h1>
            <p>현재시간 : {now}</p>
            <p>Render 서버 정상 작동중</p>
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

print(f"서버 시작 : {port}")

HTTPServer(("0.0.0.0", port), Handler).serve_forever()
