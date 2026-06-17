import requests
import os

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET")

print("토큰 발급 테스트 시작")

r = requests.post(
    "토스 API 토큰 주소",
    json={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
)

print(r.status_code)
print(r.text[:500])
