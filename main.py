from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests
import json

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        token_res = requests.post(
            "https://openapi.tossinvest.com/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
        )

        token = token_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}"
        }

        price_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices?symbols=000660",
            headers=headers
        )

        account_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/accounts",
            headers=headers
        )

        html = f"""
        <html>
        <body>
        <h1>토스 API 테스트</h1>

        <h2>현재가</h2>
        <pre>{json.dumps(price_res.json(), indent=2, ensure_ascii=False)}</pre>

        <h2>계좌목록</h2>
        <pre>{json.dumps(account_res.json(), indent=2, ensure_ascii=False)}</pre>

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
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
