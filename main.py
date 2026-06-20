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
    "233740": "코스닥150 레버리지",
    "494310": "반도체 레버리지",
    "0100K0": "방산 레버리지",
    "0080Y0": "조선 레버리지",
    "462330": "2차전지 레버리지",
    "0177X0": "로봇 휴머노이드",
    "433500": "원자력",
    "418660": "나스닥100 레버리지",
}

ALL_STOCKS = {**MAIN_STOCKS, **WATCH_STOCKS}

state = {
    "token": None,
    "token_time": None,
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
    "last_update": None,
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
        state["token_time"] = datetime.now(KST)
        return token
    except Exception as e:
        print(f"토큰 오류: {e}")
        return None

def get_prices():
    try:
        if not state["token"]:
            get_token()
        symbols = ",".join(ALL_STOCKS.keys())
        res = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices",
            headers={"Authorization": f"Bearer {state['token']}"},
            params={"symbols": symbols},
            timeout=10
        )
        data = res.json()
        now = datetime.now(KST)
        for item in data if isinstance(data, list) else data.get("prices", []):
            symbol = item.get("symbol", item.get("stockCode", ""))
            price = float(item.get("price", item.get("currentPrice", 0)))
            volume = float(item.get("volume", item.get("tradingVolume", 0)))
            if symbol and price:
                state["prev_prices"][symbol] = state["prices"].get(symbol, price)
                state["prev_volumes"][symbol] = state["volumes"].get(symbol, volume)
                state["prices"][symbol] = price
                state["volumes"][symbol] = volume
                if symbol not in state["high_prices"]:
                    state["high_prices"][symbol] = price
                    state["low_prices"][symbol] = price
                else:
                    state["high_prices"][symbol] = max(state["high_prices"][symbol], price)
                    state["low_prices"][symbol] = min(state["low_prices"][symbol], price)
        state["last_update"] = now.strftime("%H:%M:%S")
        return True
    except Exception as e:
        print(f"가격 조회 오류: {e}")
        if "401" in str(e) or "token" in str(e).lower():
            get_token()
        return False

def send_kakao(msg):
    if not KAKAO_TOKEN:
        print(f"[알림] {msg}")
        return
    try:
        requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {KAKAO_TOKEN}"},
            data={
                "template_object": json.dumps({
                    "object_type": "text",
                    "text": msg,
                    "link": {"web_url": "", "mobile_web_url": ""}
                })
            },
            timeout=5
        )
        now = datetime.now(KST).strftime("%H:%M:%S")
        state["alerts"].insert(0, {"time": now, "msg": msg})
        if len(state["alerts"]) > 20:
            state["alerts"] = state["alerts"][:20]
    except Exception as e:
        print(f"카카오 오류: {e}")

def fetch_news():
    try:
        res = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        keywords_bad = ["규제", "하락", "적자", "감산", "연기", "취소", "철회", "정정", "제재"]
        keywords_good = ["수주", "호실적", "상향", "급등", "AI", "HBM", "엔비디아"]
        for kw in keywords_bad:
            if kw in res.text:
                news_item = {"time": datetime.now(KST).strftime("%H:%M"), "title": f"⚠️ 악재: {kw}", "type": "bad"}
                if news_item not in state["news"]:
                    state["news"].insert(0, news_item)
                    send_kakao(f"📰 악재 뉴스!\n키워드: {kw}\n→ 매도 고려하세요")
        for kw in keywords_good:
            if kw in res.text:
                news_item = {"time": datetime.now(KST).strftime("%H:%M"), "title": f"✅ 호재: {kw}", "type": "good"}
                if news_item not in state["news"]:
                    state["news"].insert(0, news_item)
        if len(state["news"]) > 20:
            state["news"] = state["news"][:20]
    except Exception as e:
        print(f"뉴스 오류: {e}")

def check_signals():
    now = datetime.now(KST)
    if not (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
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
    vol_change = (curr_vol - prev_vol) / prev_vol * 100 if prev_vol > 0 else 0
    high_drop = (price - high) / high * 100 if high > 0 else 0
    low_rise = (price - low) / low * 100 if low > 0 else 0
    profit = (price - buy_price) / buy_price * 100 if buy_price > 0 else 0
    if buy_price > 0:
        for pct in [1, 2, 3, 5, 7, 10]:
            if profit >= pct:
                send_kakao(f"💰 수익 +{pct}% 달성!\n0193T0: {price:,.0f}원\n매수가: {buy_price:,.0f}원\n수익률: +{profit:.1f}%")
                break
    if high_drop <= -5 and vol_change < -20:
        send_kakao(f"🔴 매도 신호!\n0193T0: {price:,.0f}원\n고점 대비: {high_drop:.1f}%\n거래량 감소: {vol_change:.0f}%\n→ 레버리지 매도 / 인버스 고려")
        state["paper_trades"].insert(0, {"time": now.strftime("%H:%M"), "action": "매도신호", "price": price, "reason": f"고점대비{high_drop:.1f}%"})
    if low_rise >= 3 and vol_change > 20:
        send_kakao(f"🟢 재매수 신호!\n0193T0: {price:,.0f}원\n저점 대비: +{low_rise:.1f}%\n거래량 증가: +{vol_change:.0f}%\n→ 레버리지 재매수 타임")
        state["paper_trades"].insert(0, {"time": now.strftime("%H:%M"), "action": "매수신호", "price": price, "reason": f"저점대비+{low_rise:.1f}%"})
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
    minute_counter = 0
    while True:
        try:
            now = datetime.now(KST)
            reset_daily()
            if 9 <= now.hour < 16:
                get_prices()
                check_signals()
            if minute_counter % 5 == 0:
                fetch_news()
            if minute_counter % 30 == 0:
                get_token()
            minute_counter += 1
            time.sleep(60)
        except Exception as e:
            print(f"루프 오류: {e}")
            time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path

        if path == '/test_kakao':
            send_kakao(f"✅ 카카오 테스트!\n80억 프로젝트 정상 작동\n시간: {datetime.now(KST).strftime('%H:%M:%S')} KST")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>✅ 카카오 전송됨! 카카오톡 확인해봐</h2>".encode("utf-8"))
            return

        if path.startswith("/set_buy"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(path).query)
            price = float(params.get("price", [0])[0])
            state["buy_price"] = price
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "buy_price": price}).encode())
            return

        now = datetime.now(KST)
        stock_rows = ""
        for code, name in ALL_STOCKS.items():
            price = state["prices"].get(code, 0)
            prev = state["prev_prices"].get(code,
