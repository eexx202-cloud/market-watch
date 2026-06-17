from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET")

TOKEN_RESULT = "아직 테스트 안함"

try:
    r = requests.post(
        "https://openapi.tossinvest.com/oauth2/token",
        json={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        },
        timeout=10
    )

    TOKEN_RESULT = f"STATUS={r.status_code}<br>{r.text[:500]}"

except Exception as e:
    TOKEN_RESULT = str(e)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"""
        <html>
        <body>
        <h1>80억 프로젝트</h1>

        <p>ACCOUNT : {bool(os.environ.get('TOSS_ACCOUNT'))}</p>
        <p>CLIENT_ID : {bool(os.environ.get('TOSS_CLIENT_ID'))}</p>
        <p>CLIENT_SECRET : {bool(os.environ.get('TOSS_CLIENT_SECRET'))}</p>

        <hr>

        <h3>토큰 테스트</h3>
        <p>{TOKEN_RESULT}</p>

        </body>
        </html>
        """

        self.send_response(200)
        self.end_headers()
        self.wfile.write(html.encode())

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
