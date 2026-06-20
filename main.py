from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        # 토큰 발급
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

        # SK하이닉스 현재가 조회
        price_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices?symbols=000660",
            headers=headers
        )

        html = f"""
        <html>
        <body>
        <h1>SK하이닉스 현재가 테스트</h1>

        <h2>토큰</h2>
        <pre>{token_res.text}</pre>

        <h2>현재가</h2>
        <pre>{price_res.text}</pre>

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
