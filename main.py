from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
import html
import requests
from datetime import datetime
from urllib.parse import urlparse
import pytz


# ============================================================
# 기본 설정
# ============================================================

KST = pytz.timezone("Asia/Seoul")
PORT = int(os.environ.get("PORT", "10000"))

KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "").strip()
APP_URL = os.environ.get("APP_URL", "").strip()


def now_text():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def safe(v):
    return html.escape(str(v))


def mask_token(token):
    if not token:
        return "없음"
    if len(token) < 16:
        return f"너무 짧음 / 길이 {len(token)}"
    return f"{token[:8]} ... {token[-8:]} / 길이 {len(token)}"


# ============================================================
# 카카오 토큰 확인
# ============================================================

def check_kakao_token():
    if not KAKAO_TOKEN:
        return False, "KAKAO_TOKEN 환경변수가 없습니다."

    try:
        r = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={
                "Authorization": "Bearer " + KAKAO_TOKEN
            },
            timeout=10,
        )

        return r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"

    except Exception as e:
        return False, "예외 발생\n" + str(e)


# ============================================================
# 카카오톡 나에게 보내기
# ============================================================

def send_kakao_message():
    if not KAKAO_TOKEN:
        return False, "KAKAO_TOKEN 환경변수가 없습니다."

    template = {
        "object_type": "text",
        "text": "✅ 카카오톡 테스트 성공\n" + now_text(),
        "link": {
            "web_url": APP_URL or "https://developers.kakao.com",
            "mobile_web_url": APP_URL or "https://developers.kakao.com",
        },
    }

    try:
        r = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={
                "Authorization": "Bearer " + KAKAO_TOKEN,
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            },
            data={
                "template_object": json.dumps(template, ensure_ascii=False)
            },
            timeout=10,
        )

        return r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"

    except Exception as e:
        return False, "예외 발생\n" + str(e)


# ============================================================
# 웹 서버
# ============================================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            self.home()
            return

        if path == "/env":
            self.env_page()
            return

        if path == "/check_token":
            ok, msg = check_kakao_token()
            title = "토큰 확인 성공" if ok else "토큰 확인 실패"
            self.result_page(title, msg)
            return

        if path == "/test_kakao":
            ok, msg = send_kakao_message()
            title = "카카오톡 실제 전송 성공" if ok else "카카오톡 실제 전송 실패"
            self.result_page(title, msg)
            return

        self.html_response("""
        <h1>없는 주소</h1>
        <a href="/">돌아가기</a>
        """)

    def home(self):
        self.html_response(f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>카카오톡 단독 테스트</title>
<style>
body {{
    background: #080808;
    color: white;
    font-family: Arial, sans-serif;
    padding: 30px;
}}
.card {{
    background: #151515;
    border: 1px solid #333;
    border-radius: 14px;
    padding: 24px;
    max-width: 760px;
}}
h1 {{
    font-size: 34px;
}}
button {{
    padding: 14px 20px;
    margin: 8px 6px;
    border: 0;
    border-radius: 8px;
    font-weight: bold;
    cursor: pointer;
}}
.yellow {{
    background: #ffe812;
    color: #111;
}}
.gray {{
    background: #333;
    color: white;
}}
pre {{
    background: #000;
    color: #00ff66;
    padding: 16px;
    white-space: pre-wrap;
}}
a {{
    color: #ffe812;
}}
</style>
</head>
<body>
<div class="card">
    <h1>카카오톡 단독 테스트</h1>

    <pre>시간: {now_text()}
KAKAO_TOKEN: {safe(mask_token(KAKAO_TOKEN))}
APP_URL: {safe(APP_URL)}</pre>

    <button class="gray" onclick="location.href='/env'">0. 환경변수 확인</button>
    <button class="gray" onclick="location.href='/check_token'">1. 토큰 확인</button>
    <button class="yellow" onclick="location.href='/test_kakao'">2. 카카오톡 보내기</button>

    <p>
    순서대로 눌러.<br>
    먼저 <b>환경변수 확인</b> → <b>토큰 확인</b> → <b>카카오톡 보내기</b>.
    </p>

    <p>
    성공 기준:<br>
    토큰 확인: <b>HTTP 200</b><br>
    카카오톡 보내기: <b>HTTP 200 / {{}}</b>
    </p>
</div>
</body>
</html>
""")

    def env_page(self):
        self.result_page(
            "환경변수 확인",
            f"KAKAO_TOKEN: {mask_token(KAKAO_TOKEN)}\nAPP_URL: {APP_URL}\n시간: {now_text()}"
        )

    def result_page(self, title, msg):
        self.html_response(f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{safe(title)}</title>
<style>
body {{
    background: #080808;
    color: white;
    font-family: Arial, sans-serif;
    padding: 30px;
}}
h1 {{
    font-size: 34px;
}}
pre {{
    background: #000;
    color: #00ff66;
    padding: 16px;
    white-space: pre-wrap;
}}
a {{
    color: #ffe812;
    font-size: 22px;
}}
</style>
</head>
<body>
<h1>{safe(title)}</h1>
<pre>{safe(msg)}</pre>
<a href="/">돌아가기</a>
</body>
</html>
""")

    def html_response(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print("카카오톡 단독 테스트 서버 시작:", PORT)
    print("KAKAO_TOKEN:", mask_token(KAKAO_TOKEN))
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
