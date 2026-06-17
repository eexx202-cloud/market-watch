from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import os

print("ACCOUNT:", bool(os.environ.get("TOSS_ACCOUNT")))
print("CLIENT_ID:", bool(os.environ.get("TOSS_CLIENT_ID")))
print("CLIENT_SECRET:", bool(os.environ.get("TOSS_CLIENT_SECRET")))

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
        self.end_headers()
        self.wfile.write(html.encode())

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
