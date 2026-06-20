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

# ============================================================
# 감시 종목
# ============================================================
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

# ============================================================
# 전역 상태
# ============================================================
state = {
    "token": None,
    "token_time": None,
    "prices": {},        # 현재가
    "prev_prices": {},   # 이전 가격
    "high_prices": {},   # 장중 고점
    "low_prices": {},    # 장중 저점
    "volumes": {},       # 현재 거래량
    "prev_volumes": {},  # 이전 거래량
    "buy_price": float(os.environ.get("BUY_PRICE", "0")),  # 내 매수가
    "alerts": [],        # 알림 기록
    "paper_trades": [],  # 페이퍼 트레이딩
    "news": [],          # 뉴스
    "last_update": None,
}

# ============================================================
# 토스 API
# ============================================================
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
                
                # 장중 고점/저점 갱신
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

# ============================================================
# 카카오 알림
# ============================================================
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

# ============================================================
# 뉴스 수집
# ============================================================
def fetch_news():
    try:
        import xml.etree.ElementTree as ET
        res = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        keywords_bad = ["규제", "하락", "적자", "감산", "연기", "취소", "철회", "정정", "제재"]
        keywords_good = ["수주", "호실적", "상향", "급등", "AI", "HBM", "엔비디아"]
        
        for kw in keywords_bad:
            if kw in res.text:
                news_item = {"time": datetime.now(KST).strftime("%H:%M"), "title": f"⚠️ 악재 키워드 감지: {kw}", "type": "bad"}
                if news_item not in state["news"]:
                    state["news"].insert(0, news_item)
                    send_kakao(f"📰 악재 뉴스!\n키워드: {kw}\n→ 매도 고려하세요")
        
        for kw in keywords_good:
            if kw in res.text:
                news_item = {"time": datetime.now(KST).strftime("%H:%M"), "title": f"✅ 호재 키워드 감지: {kw}", "type": "good"}
                if news_item not in state["news"]:
                    state["news"].insert(0, news_item)
        
        if len(state["news"]) > 20:
            state["news"] = state["news"][:20]
    except Exception as e:
        print(f"뉴스 오류: {e}")

# ============================================================
# 신호 감지
# ============================================================
def check_signals():
    now = datetime.now(KST)
    
    # 장 시간 체크 (9:00~15:30)
    if not (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
        return
    
    lev = "0193T0"
    inv = "0197X0"
    
    if lev not in state["prices"]:
        return
    
    price = state["prices"][lev]
    high = state["high_prices"].get(lev, price)
    low = state["low_prices"].get(lev, price)
    prev_vol = state["prev_volumes"].get(lev, 0)
    curr_vol = state["volumes"].get(lev, 0)
    buy_price = state["buy_price"]
    
    # 거래량 변화
    vol_change = (curr_vol - prev_vol) / prev_vol * 100 if prev_vol > 0 else 0
    
    # 고점 대비 하락
    high_drop = (price - high) / high * 100 if high > 0 else 0
    
    # 저점 대비 반등
    low_rise = (price - low) / low * 100 if low > 0 else 0
    
    # 매수가 대비 수익
    profit = (price - buy_price) / buy_price * 100 if buy_price > 0 else 0
    
    # 수익 알림 (매수가 기준)
    if buy_price > 0:
        for pct in [1, 2, 3, 5, 7, 10]:
            if profit >= pct:
                msg = f"💰 수익 +{pct}% 달성!\n0193T0 현재가: {price:,.0f}원\n매수가: {buy_price:,.0f}원\n수익률: +{profit:.1f}%"
                key = f"profit_{pct}"
                if key not in [a.get("key") for a in state["alerts"]]:
                    send_kakao(msg)
                    state["alerts"][0]["key"] = key if state["alerts"] else None
                break
    
    # 🔴 매도 신호: 고점 대비 -5% + 거래량 감소
    if high_drop <= -5 and vol_change < -20:
        send_kakao(
            f"🔴 매도 신호!\n"
            f"0193T0: {price:,.0f}원\n"
            f"고점 대비: {high_drop:.1f}%\n"
            f"거래량 감소: {vol_change:.0f}%\n"
            f"→ 레버리지 매도 / 인버스 고려"
        )
        # 페이퍼 트레이딩 기록
        state["paper_trades"].insert(0, {
            "time": now.strftime("%H:%M"),
            "action": "매도신호",
            "price": price,
            "reason": f"고점대비{high_drop:.1f}%"
        })
    
    # 🟢 재매수 신호: 저점 대비 +3% + 거래량 증가
    if low_rise >= 3 and vol_change > 20:
        send_kakao(
            f"🟢 재매수 신호!\n"
            f"0193T0: {price:,.0f}원\n"
            f"저점 대비: +{low_rise:.1f}%\n"
            f"거래량 증가: +{vol_change:.0f}%\n"
            f"→ 레버리지 재매수 타임"
        )
        state["paper_trades"].insert(0, {
            "time": now.strftime("%H:%M"),
            "action": "매수신호",
            "price": price,
            "reason": f"저점대비+{low_rise:.1f}%"
        })
    
    if len(state["paper_trades"]) > 50:
        state["paper_trades"] = state["paper_trades"][:50]

# ============================================================
# 장 시작 초기화
# ============================================================
def reset_daily():
    now = datetime.now(KST)
    if now.hour == 9 and now.minute == 0:
        state["high_prices"] = {}
        state["low_prices"] = {}
        print("장 시작 - 고점/저점 초기화")

# ============================================================
# 메인 루프
# ============================================================
def main_loop():
    get_token()
    print("시스템 시작")
    
    minute_counter = 0
    
    while True:
        try:
            now = datetime.now(KST)
            reset_daily()
            
            # 장 시간에만 가격 수집
            if 9 <= now.hour < 16:
                get_prices()
                check_signals()
            
            # 5분마다 뉴스 수집
            if minute_counter % 5 == 0:
                fetch_news()
            
            # 30분마다 토큰 갱신
            if minute_counter % 30 == 0:
                get_token()
            
            minute_counter += 1
            time.sleep(60)  # 1분마다
            
        except Exception as e:
            print(f"루프 오류: {e}")
            time.sleep(60)

# ============================================================
# 웹 대시보드
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path
        
        # 매수가 설정
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
        
        # 종목별 현재가 HTML
        stock_rows = ""
        for code, name in ALL_STOCKS.items():
            price = state["prices"].get(code, 0)
            prev = state["prev_prices"].get(code, price)
            high = state["high_prices"].get(code, price)
            low = state["low_prices"].get(code, price)
            
            chg = (price - prev) / prev * 100 if prev > 0 else 0
            high_drop = (price - high) / high * 100 if high > 0 else 0
            
            color = "#ff4444" if chg > 0 else "#4444ff" if chg < 0 else "#ffffff"
            bg = "#2a0000" if code in MAIN_STOCKS else "#1a1a2e"
            
            stock_rows += f"""
            <tr style="background:{bg}">
                <td>{code}</td>
                <td><b>{name}</b></td>
                <td style="color:{color}">{price:,.0f}원</td>
                <td style="color:{color}">{chg:+.2f}%</td>
                <td>{high:,.0f}</td>
                <td style="color:#ff8800">{high_drop:+.1f}%</td>
            </tr>"""
        
        # 알림 목록
        alert_rows = ""
        for a in state["alerts"][:10]:
            alert_rows += f'<tr><td>{a["time"]}</td><td>{a["msg"]}</td></tr>'
        
        # 뉴스 목록
        news_rows = ""
        for n in state["news"][:5]:
            color = "#ff4444" if n["type"] == "bad" else "#44ff44"
            news_rows += f'<tr><td>{n["time"]}</td><td style="color:{color}">{n["title"]}</td></tr>'
        
        # 페이퍼 트레이딩
        trade_rows = ""
        for t in state["paper_trades"][:10]:
            color = "#ff4444" if "매도" in t["action"] else "#44ff44"
            trade_rows += f'<tr><td>{t["time"]}</td><td style="color:{color}">{t["action"]}</td><td>{t["price"]:,.0f}</td><td>{t["reason"]}</td></tr>'
        
        buy_price = state["buy_price"]
        lev_price = state["prices"].get("0193T0", 0)
        profit = (lev_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
        profit_color = "#ff4444" if profit > 0 else "#4444ff"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>80억 프로젝트</title>
    <meta http-equiv="refresh" content="60">
    <style>
        body {{ background:#0a0a0a; color:#fff; font-family:Arial; padding:10px; }}
        h1 {{ color:#ffd700; text-align:center; }}
        h2 {{ color:#aaa; border-bottom:1px solid #333; padding-bottom:5px; }}
        table {{ width:100%; border-collapse:collapse; margin-bottom:20px; }}
        th {{ background:#1a1a3e; padding:8px; text-align:left; }}
        td {{ padding:6px; border-bottom:1px solid #222; }}
        .profit {{ font-size:24px; text-align:center; padding:10px; background:#1a1a1a; border-radius:8px; margin:10px 0; }}
        input {{ background:#222; color:#fff; border:1px solid #555; padding:8px; border-radius:4px; }}
        button {{ background:#ffd700; color:#000; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-weight:bold; }}
    </style>
</head>
<body>
    <h1>🏦 80억 프로젝트</h1>
    <p style="text-align:center;color:#888">마지막 업데이트: {state['last_update']} KST</p>
    
    <div class="profit">
        <div>0193T0 현재가: <b style="color:#ffd700">{lev_price:,.0f}원</b></div>
        <div>내 매수가: {buy_price:,.0f}원</div>
        <div style="color:{profit_color}">수익률: {profit:+.1f}%</div>
    </div>
    
    <div style="text-align:center;margin:10px 0">
        <input type="number" id="buy_price" placeholder="매수가 입력" value="{buy_price:.0f}">
        <button onclick="setBuyPrice()">매수가 설정</button>
    </div>
    
    <h2>📊 종목 현황</h2>
    <table>
        <tr><th>코드</th><th>종목명</th><th>현재가</th><th>등락</th><th>장중고점</th><th>고점대비</th></tr>
        {stock_rows}
    </table>
    
    <h2>📱 알림 기록</h2>
    <table>
        <tr><th>시간</th><th>내용</th></tr>
        {alert_rows if alert_rows else '<tr><td colspan="2" style="color:#888">알림 없음</td></tr>'}
    </table>
    
    <h2>📰 뉴스</h2>
    <table>
        <tr><th>시간</th><th>내용</th></tr>
        {news_rows if news_rows else '<tr><td colspan="2" style="color:#888">뉴스 없음</td></tr>'}
    </table>
    
    <h2>📈 페이퍼 트레이딩</h2>
    <table>
        <tr><th>시간</th><th>신호</th><th>가격</th><th>이유</th></tr>
        {trade_rows if trade_rows else '<tr><td colspan="4" style="color:#888">신호 없음</td></tr>'}
    </table>

    <script>
    function setBuyPrice() {{
        var price = document.getElementById('buy_price').value;
        fetch('/set_buy?price=' + price)
            .then(r => r.json())
            .then(d => alert('매수가 설정: ' + d.buy_price + '원'));
    }}
    </script>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    
    def log_message(self, format, *args):
        pass  # 로그 억제

# ============================================================
# 실행
# ============================================================
threading.Thread(target=main_loop, daemon=True).start()

port = int(os.environ.get("PORT", 10000))
print(f"서버 시작: {port}포트")
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
