from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET")

r = requests.post(
    "https://openapi.tossinvest.com/oauth2/token",
    headers={
        "Content-Type": "application/x-www-form-urlencoded"
    },
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
)

RESULT = f"""
STATUS={r.status_code}

{r.text}
"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"<h1>80억 프로젝트</h1><pre>{RESULT}</pre>"

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
