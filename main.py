from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET")

try:
    r = requests.post(
        "https://openapi.tossinvest.com/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        },
        timeout=10
    )

    TOKEN_RESULT = f"""
    STATUS={r.status_code}
    <br><br>
    {r.text}
    """

except Exception as e:
    TOKEN_RESULT = str(e)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"""
        <html>
        <body>
        <h1>80억 프로젝트</h1>
        <pre>{TOKEN_RESULT}</pre>
        </body>
        </html>
        """

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
