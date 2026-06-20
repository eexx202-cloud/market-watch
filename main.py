from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests
import json

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

        # 현재가 조회
        price_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices?symbols=000660",
            headers=headers
        )

        # 계좌 조회
        account_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/accounts",
            headers=headers
        )

        account_data = account_res.json()
        account_seq = account_data["result"][0]["accountSeq"]

        # 보유주식 조회
        holding_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/holdings",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tossinvest-Account": str(account_seq)
            }
        )

        # 매수가능금액 조회
        buying_res = requests.get(
            "https://openapi.tossinvest.com/api/v1/buying-power?market=KR",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tossinvest-Account": str(account_seq)
            }
        )

        html = f"""
        <html>
        <body>

        <h1>토스 API 테스트</h1>

        <h2>현재가</h2>
        <pre>{json.dumps(price_res.json(), indent=2, ensure_ascii=False)}</pre>

        <h2>계좌목록</h2>
        <pre>{json.dumps(account_data, indent=2, ensure_ascii=False)}</pre>

        <h2>보유주식</h2>
        <pre>{json.dumps(holding_res.json(), indent=2, ensure_ascii=False)}</pre>

        <h2>매수가능금액 상태코드</h2>
        <pre>{buying_res.status_code}</pre>

        <h2>매수가능금액 원본응답</h2>
        <pre>{buying_res.text}</pre>

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
