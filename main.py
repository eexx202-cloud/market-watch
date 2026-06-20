from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests
import threading
import time
import json
from datetime import datetime
import pytz

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")
KST = pytz.timezone('Asia/Seoul')

MAIN_STOCKS = {
    "0193T0": "하이닉스 레버리지",
    "0197X0": "하이닉스 인버스",
    "000660": "하이닉스 원주",
}

WATCH_STOCKS = {
    "0193W0": "삼성전자 레버리지",
    "0193L0": "삼성전자 인버스",
    "005930": "삼성전자 원주",
    "122630": "KODEX 레버리지",
    "252670": "KODEX 인버스2X",
    "069500": "KODEX 200",
    "233740": "코스닥150 레버리지",
    "251340": "코스닥150 인버스",
    "229200": "KODEX 코스닥150",
    "494310": "반도체 레버리지",
    "488080": "TIGER 반도체TOP10레버리지",
    "469150": "AI반도체",
    "0100K0": "방산 레버리지",
    "0080Y0": "조선 레버리지",
    "462330": "2차전지 레버리지",
    "0177X0": "로봇 휴머노이드",
    "445290": "로봇액티브",
    "433500": "원자력",
    "487240": "AI전력인프라",
    "418660": "나스닥100 레버리지",
    "465610": "미국빅테크TOP7 레버리지",
    "225040": "S&P500 레버리지",
    "0127R0": "AI클라우드",
}

ALL_STOCKS = {}
ALL_STOCKS.update(MAIN_STOCKS)
ALL_STOCKS.update(WATCH_STOCKS)

state = {
    "token": None,
    "prices": {},
    "prev_prices": {},
    "high_prices": {},
    "low_prices": {},
    "volumes": {},
    "prev_volumes": {},
    "buy_price": float(os.environ.get("BUY_PRICE", "0")),
    "alerts": [],
    "paper_trades": [],
    "news": [],
    "last_update": "없음",
}


def get_token():
    try:
        res = requests.post(
            "https://openapi.tossinvest.com/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            },
            timeout=10
        )
        token = res.json().get("access_token")
        state["token"] = token
        return token
    except Exception as e:
        print("토큰 오류: " + str(e))
        return None


def get_prices():
    try:
        if not state["token"]:
            get_token()
        symbols = ",".join(ALL_STOCKS.keys())
        res = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices",
            headers={"Authorization": "Bearer " + str(state["token"])},
            params={"symbols": symbols},
            timeout=10
        )
        data = res.json()
        now = datetime.now(KST)
        items = data if isinstance(data, list) else data.get("prices", [])
        for item in items:
            symbol = item.get("symbol", item.get("stockCode", ""))
            price = float(item.get("price", item.get("currentPrice", 0)))
            volume = float(item.get("volume", item.get("tradingVolume", 0)))
            if symbol and price:
                prev_p = state["prices"].get(symbol, price)
                prev_v = state["volumes"].get(symbol, volume)
                state["prev_prices"][symbol] = prev_p
                state["prev_volumes"][symbol] = prev_v
                state["prices"][symbol] = price
                state["volumes"][symbol] = volume
                if symbol not in state["high_prices"]:
                    state["high_prices"][symbol] = price
                    state["low_prices"][symbol] = price
                else:
                    if price > state["high_prices"][symbol]:
                        state["high_prices"][symbol] = price
                    if price < state["low_prices"][symbol]:
                        state["low_prices"][symbol] = price
        state["last_update"] = now.strftime("%H:%M:%S")
        return True
    except Exception as e:
        print("가격 오류: " + str(e))
        return False


def send_kakao(msg):
    if not KAKAO_TOKEN:
        print("[알림] " + msg)
        return
    try:
        template = json.dumps({
            "object_type": "text",
            "text": msg,
            "link": {"web_url": "", "mobile_web_url": ""}
        })
        requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": "Bearer " + KAKAO_TOKEN},
            data={"template_object": template},
            timeout=5
        )
        now = datetime.now(KST).strftime("%H:%M:%S")
        state["alerts"].insert(0, {"time": now, "msg": msg})
        if len(state["alerts"]) > 20:
            state["alerts"] = state["alerts"][:20]
    except Exception as e:
        print("카카오 오류: " + str(e))


def fetch_news():
    try:
        res = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        keywords_bad = ["규제", "하락", "적자", "감산", "연기", "취소", "제재"]
        keywords_good = ["수주", "호실적", "상향", "AI", "HBM", "엔비디아"]
        now_str = datetime.now(KST).strftime("%H:%M")
        for kw in keywords_bad:
            if kw in res.text:
                item = {"time": now_str, "title": "악재: " + kw, "type": "bad"}
                state["news"].insert(0, item)
                send_kakao("악재 뉴스!\n키워드: " + kw + "\n매도 고려하세요")
                break
        for kw in keywords_good:
            if kw in res.text:
                item = {"time": now_str, "title": "호재: " + kw, "type": "good"}
                state["news"].insert(0, item)
                break
        if len(state["news"]) > 20:
            state["news"] = state["news"][:20]
    except Exception as e:
        print("뉴스 오류: " + str(e))


def check_signals():
    now = datetime.now(KST)
    if now.hour < 9 or now.hour >= 16:
        return
    lev = "0193T0"
    if lev not in state["prices"]:
        return
    price = state["prices"][lev]
    high = state["high_prices"].get(lev, price)
    low = state["low_prices"].get(lev, price)
    prev_vol = state["prev_volumes"].get(lev, 0)
    curr_vol = state["volumes"].get(lev, 0)
    buy_price = state["buy_price"]

    if prev_vol > 0:
        vol_change = (curr_vol - prev_vol) / prev_vol * 100
    else:
        vol_change = 0

    if high > 0:
        high_drop = (price - high) / high * 100
    else:
        high_drop = 0

    if low > 0:
        low_rise = (price - low) / low * 100
    else:
        low_rise = 0

    if buy_price > 0:
        profit = (price - buy_price) / buy_price * 100
        for pct in [1, 2, 3, 5, 7, 10]:
            if profit >= pct:
                send_kakao(
                    "수익 +" + str(pct) + "% 달성!\n"
                    "0193T0: " + str(int(price)) + "원\n"
                    "매수가: " + str(int(buy_price)) + "원\n"
                    "수익률: +" + str(round(profit, 1)) + "%"
                )
                break

    if high_drop <= -5 and vol_change < -20:
        send_kakao(
            "매도 신호!\n"
            "0193T0: " + str(int(price)) + "원\n"
            "고점 대비: " + str(round(high_drop, 1)) + "%\n"
            "거래량 감소\n"
            "레버리지 매도 / 인버스 고려"
        )
        state["paper_trades"].insert(0, {
            "time": now.strftime("%H:%M"),
            "action": "매도신호",
            "price": price,
            "reason": "고점대비" + str(round(high_drop, 1)) + "%"
        })

    if low_rise >= 3 and vol_change > 20:
        send_kakao(
            "재매수 신호!\n"
            "0193T0: " + str(int(price)) + "원\n"
            "저점 대비: +" + str(round(low_rise, 1)) + "%\n"
            "거래량 증가\n"
            "레버리지 재매수 타임"
        )
        state["paper_trades"].insert(0, {
            "time": now.strftime("%H:%M"),
            "action": "매수신호",
            "price": price,
            "reason": "저점대비+" + str(round(low_rise, 1)) + "%"
        })

    if len(state["paper_trades"]) > 50:
        state["paper_trades"] = state["paper_trades"][:50]


def reset_daily():
    now = datetime.now(KST)
    if now.hour == 9 and now.minute == 0:
        state["high_prices"] = {}
        state["low_prices"] = {}


def main_loop():
    get_token()
    print("시스템 시작")
    counter = 0
    while True:
        try:
            now = datetime.now(KST)
            reset_daily()
            if 9 <= now.hour < 16:
                get_prices()
                check_signals()
            if counter % 5 == 0:
                fetch_news()
            if counter % 30 == 0:
                get_token()
            counter += 1
            time.sleep(60)
        except Exception as e:
            print("루프 오류: " + str(e))
            time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path

        if path == "/test_kakao":
            now_str = datetime.now(KST).strftime("%H:%M:%S")
            send_kakao("카카오 테스트!\n80억 프로젝트 정상 작동\n시간: " + now_str + " KST")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>카카오 전송됨! 카카오톡 확인해봐</h2>".encode("utf-8"))
            return

        if path.startswith("/set_buy"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(path).query)
            price = float(params.get("price", ["0"])[0])
            state["buy_price"] = price
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "buy_price": price}).encode())
            return

        stock_rows = ""
        for code in ALL_STOCKS:
            name = ALL_STOCKS[code]
            price = state["prices"].get(code, 0)
            prev = state["prev_prices"].get(code, price)
            high = state["high_prices"].get(code, price)
            if prev > 0:
                chg = (price - prev) / prev * 100
            else:
                chg = 0
            if high > 0:
                high_drop = (price - high) / high * 100
            else:
                high_drop = 0
            if chg > 0:
                color = "#ff4444"
            elif chg < 0:
                color = "#4444ff"
            else:
                color = "#ffffff"
            if code in MAIN_STOCKS:
                bg = "#2a0000"
            else:
                bg = "#1a1a2e"
            stock_rows += (
                '<tr style="background:' + bg + '">'
                '<td>' + code + '</td>'
                '<td><b>' + name + '</b></td>'
                '<td style="color:' + color + '">' + str(int(price)) + '원</td>'
                '<td style="color:' + color + '">' + str(round(chg, 2)) + '%</td>'
                '<td>' + str(int(high)) + '</td>'
                '<td style="color:#ff8800">' + str(round(high_drop, 1)) + '%</td>'
                '</tr>'
            )

        alert_rows = ""
        for a in state["alerts"][:10]:
            alert_rows += '<tr><td>' + a["time"] + '</td><td>' + a["msg"] + '</td></tr>'
        if not alert_rows:
            alert_rows = '<tr><td colspan="2" style="color:#888">없음</td></tr>'

        news_rows = ""
        for n in state["news"][:5]:
            if n["type"] == "bad":
                nc = "#ff4444"
            else:
                nc = "#44ff44"
            news_rows += '<tr><td>' + n["time"] + '</td><td style="color:' + nc + '">' + n["title"] + '</td></tr>'
        if not news_rows:
            news_rows = '<tr><td colspan="2" style="color:#888">없음</td></tr>'

        trade_rows = ""
        for t in state["paper_trades"][:10]:
            if "매도" in t["action"]:
                tc = "#ff4444"
            else:
                tc = "#44ff44"
            trade_rows += (
                '<tr><td>' + t["time"] + '</td>'
                '<td style="color:' + tc + '">' + t["action"] + '</td>'
                '<td>' + str(int(t["price"])) + '</td>'
                '<td>' + t["reason"] + '</td></tr>'
            )
        if not trade_rows:
            trade_rows = '<tr><td colspan="4" style="color:#888">없음</td></tr>'

        buy_price = state["buy_price"]
        lev_price = state["prices"].get("0193T0", 0)
        if buy_price > 0:
            profit = (lev_price - buy_price) / buy_price * 100
        else:
            profit = 0
        if profit > 0:
            profit_color = "#ff4444"
        else:
            profit_color = "#4444ff"

        html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>80억 프로젝트</title>
<meta http-equiv="refresh" content="60">
<style>
body{background:#0a0a0a;color:#fff;font-family:Arial;padding:10px}
h1{color:#ffd700;text-align:center}
h2{color:#aaa;border-bottom:1px solid #333;padding-bottom:5px}
table{width:100%;border-collapse:collapse;margin-bottom:20px}
th{background:#1a1a3e;padding:8px;text-align:left}
td{padding:6px;border-bottom:1px solid #222}
.profit{font-size:20px;text-align:center;padding:10px;background:#1a1a1a;border-radius:8px;margin:10px 0}
input{background:#222;color:#fff;border:1px solid #555;padding:8px;border-radius:4px;width:120px}
button{background:#ffd700;color:#000;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-weight:bold;margin:4px}
.btn-blue{background:#00b4d8}
</style>
</head>
<body>
<h1>80억 프로젝트</h1>
<p style="text-align:center;color:#888">업데이트: """ + str(state["last_update"]) + """ KST</p>
<div class="profit">
<div>0193T0: <b style="color:#ffd700">""" + str(int(lev_price)) + """원</b></div>
<div>매수가: """ + str(int(buy_price)) + """원</div>
<div style="color:""" + profit_color + """">수익률: """ + str(round(profit, 1)) + """%</div>
</div>
<div style="text-align:center;margin:10px 0">
<input type="number" id="bp" value=\"""" + str(int(buy_price)) + """\" placeholder="매수가">
<button onclick="setBuy()">매수가 설정</button>
<button class="btn-blue" onclick="location.href='/test_kakao'">카카오 테스트</button>
</div>
<h2>종목 현황 (""" + str(len(ALL_STOCKS)) + """개)</h2>
<table>
<tr><th>코드</th><th>종목명</th><th>현재가</th><th>등락</th><th>장중고점</th><th>고점대비</th></tr>
""" + stock_rows + """
</table>
<h2>알림 기록</h2>
<table><tr><th>시간</th><th>내용</th></tr>""" + alert_rows + """</table>
<h2>뉴스</h2>
<table><tr><th>시간</th><th>내용</th></tr>""" + news_rows + """</table>
<h2>페이퍼 트레이딩</h2>
<table><tr><th>시간</th><th>신호</th><th>가격</th><th>이유</th></tr>""" + trade_rows + """</table>
<script>
function setBuy(){
    var p=document.getElementById('bp').value;
    fetch('/set_buy?price='+p).then(function(r){return r.json()}).then(function(d){alert('매수가: '+d.buy_price+'원')});
}
</script>
</body>
</html>"""

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


threading.Thread(target=main_loop, daemon=True).start()
port = int(os.environ.get("PORT", 10000))
print("서버 시작: " + str(port) + "포트")
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
