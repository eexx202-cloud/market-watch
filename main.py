from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

try:
    # 토큰 발급
    token_response = requests.post(
        "https://openapi.tossinvest.com/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        },
        timeout=10
    )

    access_token = token_response.json().get("access_token")

    # 계좌 조회
    account_response = requests.get(
        "https://openapi.tossinvest.com/api/v1/accounts",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=10
    )

    # 보유주식 조회
    holding_response = requests.get(
        "https://openapi.tossinvest.com/api/v1/holdings",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tossinvest-Account": "1"
        },
        timeout=10
    )

    # 삼성전자 현재가 조회
    price_response = requests.get(
        "https://openapi.tossinvest.com/api/v1/prices",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "symbol": "005930"
        },
        timeout=10
    )

    RESULT = f"""
TOKEN_STATUS={token_response.status_code}

ACCOUNT_STATUS={account_response.status_code}

HOLDING_STATUS={holding_response.status_code}

PRICE_STATUS={price_response.status_code}

{price_response.text}
"""

except Exception as e:
    RESULT = str(e)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = f"""
<html>
<body>
<h1>80억 프로젝트</h1>
<pre>{RESULT}</pre>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
