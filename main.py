from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urlencode
from datetime import datetime
import os
import json
import csv
import html
import time
import uuid
import threading
import zipfile
import xml.etree.ElementTree as ET

import requests
import pytz

# ============================================================
# 80억 프로젝트 실전 반자동 관제센터
# - 실계좌: 자동매수/자동매도 없음. 반드시 사용자가 버튼으로 최종 실행
# - 카카오: 매수/매도 확인 링크 포함
# - 26개 종목: 현재가/점수/추천수량/버튼/CSV 저장
# - AI 가상: 기본 수동. ENABLE_PAPER_AUTO=true 일 때만 가상 자동기록
# ============================================================

KST = pytz.timezone("Asia/Seoul")
BASE = os.environ.get("TOSS_BASE", "https://openapi.tossinvest.com").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
APP_URL = os.environ.get("APP_URL", "https://market-watch-6zgo.onrender.com").rstrip("/")

CLIENT_ID = os.environ.get("TOSS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("TOSS_CLIENT_SECRET", "").strip()
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

ENABLE_REAL_ORDER = os.environ.get("ENABLE_REAL_ORDER", "false").lower() == "true"
ENABLE_NEWS = os.environ.get("ENABLE_NEWS", "true").lower() == "true"
ENABLE_PAPER_AUTO = os.environ.get("ENABLE_PAPER_AUTO", "false").lower() == "true"
NEWS_REFRESH_SEC = int(os.environ.get("NEWS_REFRESH_SEC", "600"))
REFRESH_SEC = int(os.environ.get("REFRESH_SEC", "30"))
NEWS_SCORE_WEIGHT = int(os.environ.get("NEWS_SCORE_WEIGHT", "6"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
MAX_BUY_RATIO = float(os.environ.get("MAX_BUY_RATIO", "0.70"))
VIRTUAL_BASE_CASH = int(float(os.environ.get("VIRTUAL_BASE_CASH", "20000000")))
# 실계좌 보유관리 알림 기준: 고정 손절만이 아니라 시장 강도에 따라 조절됨
HOLDING_ALERT_COOLDOWN_SEC = int(os.environ.get("HOLDING_ALERT_COOLDOWN_SEC", "300"))
LOG_ROOT = os.environ.get("LOG_ROOT", "/tmp/logs")
STATE_PATH = os.environ.get("STATE_PATH", "state.json")

# 26개 감시 종목
MAIN = {
    "0193T0": "하이닉스 레버리지",
    "0197X0": "하이닉스 인버스",
    "000660": "SK하이닉스",
}
MARKET = {
    "122630": "KODEX 레버리지",
    "252670": "KODEX 인버스2X",
    "069500": "KODEX 200",
    "233740": "코스닥150 레버리지",
    "251340": "코스닥150 인버스",
    "229200": "KODEX 코스닥150",
}
WATCH = {
    "0193W0": "삼성전자 레버리지",
    "0193L0": "삼성전자 인버스",
    "005930": "삼성전자",
    "494310": "반도체 레버리지",
    "488080": "TIGER 반도체TOP10",
    "469150": "AI반도체",
    "0100K0": "방산 레버리지",
    "0080Y0": "조선 레버리지",
    "462330": "2차전지 레버리지",
    "0177X0": "로봇 휴머노이드",
    "445290": "로봇액티브",
    "433500": "원자력",
    "487240": "AI전력인프라",
    "418660": "나스닥100 레버리지",
    "465610": "미국빅테크TOP7",
    "225040": "S&P500 레버리지",
    "0127R0": "AI클라우드",
}
ALL = {**MAIN, **MARKET, **WATCH}
LEV = "0193T0"
INV = "0197X0"
HYNIX = "000660"
PRIMARY = [LEV, INV, "122630", "252670", "233740", "251340", "0193W0", "0193L0", "494310", "488080"]
# 알림 대상은 실전 핵심 종목만 제한. 미정의로 루프가 죽지 않게 반드시 정의한다.
ALERT_SYMBOLS = [LEV, INV, HYNIX, "122630", "252670", "233740", "251340"]

POSITIVE_NEWS_KEYWORDS = [
    "HBM", "엔비디아", "AI", "공급", "계약", "수주", "실적 호조", "목표가 상향", "상향", "증설",
    "흑자", "최대 실적", "반도체 회복", "수출 증가", "강세", "급등", "호재", "서프라이즈", "증가", "회복", "랠리", "투자 확대"
]
NEGATIVE_NEWS_KEYWORDS = [
    "급락", "하락", "약세", "실적 부진", "목표가 하향", "하향", "전쟁", "제재", "규제", "금리 상승", "환율 급등",
    "반도체 둔화", "수출 감소", "감산", "적자", "악재", "불확실성", "매도", "쇼크", "침체", "우려", "리스크", "관세", "제한", "공급과잉"
]
NEWS_QUERIES = ["SK하이닉스", "삼성전자 반도체", "HBM 엔비디아", "코스피 반도체", "미국 증시 반도체", "환율 금리 전쟁"]

LOCK = threading.RLock()
S = {
    "token": "",
    "token_exp": 0,
    "account_seq": "",
    "account_raw": {},
    "status": "시작 중",
    "updated": "없음",
    "last_error": "",
    "prices": {},
    "prev_prices": {},
    "history": {},
    "high": {},
    "low": {},
    "wma": {},
    "scores": {},
    "signals": {},
    "market_score": {"kospi": 0, "kosdaq": 0, "total": 0, "label": "대기"},
    "news": {"updated": "없음", "items": [], "score": 0, "label": "뉴스 대기", "positive": [], "negative": []},
    "cash": 0,
    "market_value": 0,
    "total_value": 0,
    "profit_loss": 0,
    "profit_rate": 0,
    "real_base_cash": 0,
    "holdings": [],
    "hold_qty": {},
    "sellable": {},
    "alerts": [],
    "last_alert": {},
    "orders": [],
    # 실계좌 보유관리: 내가 산 종목의 매수가/매수 후 최고가를 기억해서
    # 손절, 수익보호, 익절, 교체 후보 알림을 보냄.
    "real_watch": {},
    "paper": {
        "start_cash": 0,
        "cash": 0,
        "positions": {},
        "trades": [],
        "realized_pl": 0,
        "asset": 0,
        "profit_rate": 0,
        "last_action": "없음",
    },
}

# ============================================================
# 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)

def today():
    return now_kst().strftime("%Y-%m-%d")

def now_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")

def now_short():
    return now_kst().strftime("%H:%M:%S")

def safe(v):
    return html.escape(str(v))

def name_of(sym):
    return ALL.get(sym, sym)

def to_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            # 토스 응답은 amount.krw 형태가 많음
            for key in ["krw", "amount", "value", "cash", "quantity"]:
                if key in v:
                    return to_float(v[key], default)
            return default
        return float(str(v).replace(",", "").replace("원", "").replace("%", "").strip())
    except Exception:
        return default

def to_int(v, default=0):
    try:
        return int(to_float(v, default))
    except Exception:
        return default

def fmt_won(v):
    try:
        return f"{int(round(float(v))):,}원"
    except Exception:
        return "-"

def pct(a, b):
    try:
        if not b:
            return 0.0
        return (float(a) - float(b)) / float(b) * 100
    except Exception:
        return 0.0

def pct_text(v):
    try:
        return f"{float(v):+.2f}%"
    except Exception:
        return "+0.00%"

def color_class(v):
    try:
        v = float(v)
        if v > 0:
            return "red"
        if v < 0:
            return "blue"
    except Exception:
        pass
    return "gray"

def set_error(msg):
    print("[오류]", msg)
    with LOCK:
        S["last_error"] = f"{now_text()} {msg}"

def set_status(msg):
    with LOCK:
        S["status"] = msg
        S["updated"] = now_short()

def is_market_watch_time():
    n = now_kst()
    return 8 <= n.hour < 16

def clean_name(s):
    out = str(s)
    for ch in '\\/:*?"<>| %()[]{}':
        out = out.replace(ch, "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:80]

def day_dir():
    path = os.path.join(LOG_ROOT, today())
    os.makedirs(os.path.join(path, "symbols"), exist_ok=True)
    return path

def summary_path():
    return os.path.join(day_dir(), f"summary_{today()}.csv")

def paper_path():
    return os.path.join(day_dir(), f"paper_trades_{today()}.csv")

def orders_path():
    return os.path.join(day_dir(), f"real_orders_{today()}.csv")

def portfolio_path():
    return os.path.join(day_dir(), f"portfolio_{today()}.csv")

def swing_path():
    return os.path.join(day_dir(), f"swing_decision_{today()}.csv")

def alert_log_path():
    return os.path.join(day_dir(), f"alert_log_{today()}.csv")

def backup_zip_path():
    return os.path.join(day_dir(), f"backup_{today()}.zip")

def symbol_path(sym):
    # 실제 파일명은 한글 금지. HTTP 헤더 latin-1 오류와 502 방지.
    return os.path.join(day_dir(), "symbols", f"{sym}.csv")

def write_row(path, headers, row):
    try:
        exists = os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            if not exists:
                w.writeheader()
            w.writerow({h: row.get(h, "") for h in headers})
    except Exception as e:
        set_error(f"CSV 저장 오류: {e}")

def write_alert_log(level, kind, sym, price, profit_rate, decision, reason, sent, response=""):
    row = {
        "time": now_text(),
        "level": level,
        "kind": kind,
        "symbol": sym or "",
        "name": name_of(sym) if sym else "",
        "price": price or 0,
        "profit_rate": round(to_float(profit_rate), 2),
        "decision": decision or "",
        "reason": reason or "",
        "sent": bool(sent),
        "response": str(response)[:300],
    }
    write_row(alert_log_path(), ["time", "level", "kind", "symbol", "name", "price", "profit_rate", "decision", "reason", "sent", "response"], row)

def save_state():
    try:
        with LOCK:
            data = {"real_base_cash": S["real_base_cash"], "paper": S["paper"], "real_watch": S.get("real_watch", {})}
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        set_error(f"state 저장 실패: {e}")

def load_state():
    if not os.path.exists(STATE_PATH):
        with LOCK:
            if S["paper"].get("start_cash", 0) <= 0:
                S["paper"] = {"start_cash": VIRTUAL_BASE_CASH, "cash": VIRTUAL_BASE_CASH, "positions": {}, "trades": [], "realized_pl": 0, "asset": VIRTUAL_BASE_CASH, "profit_rate": 0, "last_action": "초기 2천만원"}
        return
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        with LOCK:
            S["real_base_cash"] = to_int(data.get("real_base_cash", 0))
            paper = data.get("paper")
            if isinstance(paper, dict):
                S["paper"].update(paper)
            rw = data.get("real_watch")
            if isinstance(rw, dict):
                S["real_watch"] = rw
            if S["paper"].get("start_cash", 0) <= 0:
                S["paper"] = {"start_cash": VIRTUAL_BASE_CASH, "cash": VIRTUAL_BASE_CASH, "positions": {}, "trades": [], "realized_pl": 0, "asset": VIRTUAL_BASE_CASH, "profit_rate": 0, "last_action": "초기 2천만원"}
    except Exception as e:
        set_error(f"state 로드 실패: {e}")

# ============================================================
# 카카오
# ============================================================

def add_alert(msg):
    with LOCK:
        S["alerts"].insert(0, {"time": now_short(), "msg": msg})
        S["alerts"] = S["alerts"][:80]

def kakao_template_text(msg, url, button_title="대시보드 열기"):
    return {
        "object_type": "text",
        "text": msg[:950],
        "link": {"web_url": url, "mobile_web_url": url},
        "button_title": button_title,
    }

def kakao_template_feed(title, desc, buttons):
    # Kakao default template feed. 버튼은 URL 이동만 하고 주문은 확인 화면에서 한번 더 눌러야 함.
    return {
        "object_type": "feed",
        "content": {
            "title": title[:80],
            "description": desc[:700],
            "image_url": "https://developers.kakao.com/assets/img/about/logos/kakaolink/kakaolink_btn_medium.png",
            "link": {"web_url": APP_URL or "https://developers.tossinvest.com/docs", "mobile_web_url": APP_URL or "https://developers.tossinvest.com/docs"},
        },
        "buttons": buttons,
    }

def post_kakao_template(template):
    if not KAKAO_TOKEN:
        return False, "KAKAO_TOKEN 없음"
    try:
        r = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": "Bearer " + KAKAO_TOKEN, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=8,
        )
        return r.status_code == 200, f"HTTP {r.status_code} {r.text[:300]}"
    except Exception as e:
        return False, str(e)

def telegram_enabled():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

def telegram_button(text, url):
    return {"text": text, "url": url}

def send_telegram(msg, buttons=None):
    # 텔레그램은 inline_keyboard 버튼이 카카오보다 안정적으로 보임.
    # 버튼을 눌러도 바로 주문하지 않고 /confirm 확인 화면으로만 이동함.
    if not telegram_enabled():
        write_alert_log("SYSTEM", "telegram", "", 0, 0, "not_sent", "TELEGRAM 설정 없음", False, "missing token/chat_id")
        return False, "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 없음"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg[:3900],
        "disable_web_page_preview": True,
    }
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons}, ensure_ascii=False)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            timeout=8,
        )
        ok = r.status_code == 200
        write_alert_log("INFO", "telegram", "", 0, 0, "sent" if ok else "failed", msg.split("\n")[0], ok, f"HTTP {r.status_code} {r.text[:300]}")
        return ok, f"HTTP {r.status_code} {r.text[:300]}"
    except Exception as e:
        write_alert_log("ERROR", "telegram", "", 0, 0, "exception", msg.split("\n")[0], False, str(e))
        return False, str(e)

def send_telegram_file(filepath, caption=""):
    if not telegram_enabled():
        return False, "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 없음"
    if not os.path.exists(filepath):
        return False, f"파일 없음: {filepath}"
    try:
        with open(filepath, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                files={"document": (os.path.basename(filepath), f)},
                timeout=30,
            )
        ok = r.status_code == 200
        write_alert_log("INFO", "telegram_file", "", 0, 0, "sent" if ok else "failed", caption, ok, f"HTTP {r.status_code} {r.text[:300]}")
        return ok, f"HTTP {r.status_code} {r.text[:300]}"
    except Exception as e:
        write_alert_log("ERROR", "telegram_file", "", 0, 0, "exception", caption, False, str(e))
        return False, str(e)

def check_telegram():
    if not TELEGRAM_BOT_TOKEN:
        return False, "TELEGRAM_BOT_TOKEN 없음"
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=8)
        return r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"
    except Exception as e:
        return False, str(e)

def send_telegram_test():
    url = APP_URL or "https://market-watch-6zgo.onrender.com"
    return send_telegram(
        "✅ 텔레그램 알림 테스트 성공\n" + now_text(),
        [[telegram_button("대시보드 열기", url)]],
    )

def send_kakao(msg, link_url=None, button_title="대시보드 열기"):
    add_alert(msg)
    url = link_url or APP_URL or "https://developers.tossinvest.com/docs"
    ok, text = post_kakao_template(kakao_template_text(msg, url, button_title))
    tg_ok, tg_text = send_telegram(msg, [[telegram_button(button_title, url)]])
    with LOCK:
        S["kakao_last"] = f"{now_text()} kakao={text} / telegram={tg_text}"
    return ok or tg_ok, f"kakao={text} / telegram={tg_text}"

def confirm_url(sym, side, qty=0):
    base = APP_URL or ""
    qs = urlencode({"symbol": sym, "side": side, "qty": str(qty)})
    return f"{base}/confirm?{qs}" if base else "/confirm?" + qs

def send_signal_kakao(sym, title):
    sig = S["signals"].get(sym, {})
    price = S["prices"].get(sym, 0)
    qty = int(sig.get("rec_buy_qty", 0) or sig.get("qty", 0) or 0)
    sellable = int(S["sellable"].get(sym, 0))
    buy_url = confirm_url(sym, "BUY", qty)
    sell_url = confirm_url(sym, "SELL", sellable or qty)
    dashboard_url = APP_URL or "https://market-watch-6zgo.onrender.com"
    desc = (
        f"{name_of(sym)}\n"
        f"현재가: {fmt_won(price)}\n"
        f"AI 점수: {sig.get('score', 0)}\n"
        f"신호: {sig.get('label', '-')}\n"
        f"시장: {S['market_score']['label']} / {S['market_score']['total']}점\n"
        f"뉴스: {S['news']['label']} / {S['news']['score']}점\n"
        f"추천매수: {qty}주 / 매도가능: {sellable}주\n"
        f"실제 주문은 확인 화면에서 직접 버튼 클릭"
    )
    kakao_buttons = [
        {"title": "매수 확인", "link": {"web_url": buy_url, "mobile_web_url": buy_url}},
        {"title": "매도 확인", "link": {"web_url": sell_url, "mobile_web_url": sell_url}},
    ]
    telegram_buttons = [
        [telegram_button("🔴 매수 확인", buy_url), telegram_button("🔵 매도 확인", sell_url)],
        [telegram_button("📊 대시보드", dashboard_url)],
    ]
    full_msg = f"{title}\n{desc}"
    add_alert(full_msg)
    kakao_ok, kakao_text = post_kakao_template(kakao_template_feed(title, desc, kakao_buttons))
    tg_ok, tg_text = send_telegram(full_msg, telegram_buttons)
    with LOCK:
        S["kakao_last"] = f"{now_text()} kakao={kakao_text} / telegram={tg_text}"
    return kakao_ok or tg_ok, f"kakao={kakao_text} / telegram={tg_text}"

def send_position_manage_alert(sym, title, detail):
    sig = S["signals"].get(sym, {})
    price = S["prices"].get(sym, 0)
    sellable = int(S["sellable"].get(sym, 0) or S["hold_qty"].get(sym, 0) or 0)
    sell_url = confirm_url(sym, "SELL", sellable)
    dashboard_url = APP_URL or "https://market-watch-6zgo.onrender.com"
    msg = (
        f"{title}\n"
        f"{name_of(sym)}\n"
        f"현재가: {fmt_won(price)}\n"
        f"AI 점수: {sig.get('score', 0)} / 신호: {sig.get('label', '-')}\n"
        f"시장: {S['market_score']['label']} / {S['market_score']['total']}점\n"
        f"뉴스: {S['news']['label']} / {S['news']['score']}점\n"
        f"{detail}\n"
        f"실제 매도는 확인 화면에서 직접 실행"
    )
    add_alert(msg)
    kakao_buttons = [
        {"title": "매도 확인", "link": {"web_url": sell_url, "mobile_web_url": sell_url}},
        {"title": "대시보드", "link": {"web_url": dashboard_url, "mobile_web_url": dashboard_url}},
    ]
    telegram_buttons = [
        [telegram_button("🔵 매도 확인", sell_url)],
        [telegram_button("📊 대시보드", dashboard_url)],
    ]
    kakao_ok, kakao_text = post_kakao_template(kakao_template_feed(title, msg, kakao_buttons))
    tg_ok, tg_text = send_telegram(msg, telegram_buttons)
    with LOCK:
        S["kakao_last"] = f"{now_text()} kakao={kakao_text} / telegram={tg_text}"
    return kakao_ok or tg_ok

def check_kakao():
    if not KAKAO_TOKEN:
        return False, "KAKAO_TOKEN 없음"
    try:
        r = requests.get("https://kapi.kakao.com/v2/user/me", headers={"Authorization": "Bearer " + KAKAO_TOKEN}, timeout=8)
        return r.status_code == 200, f"HTTP {r.status_code}\n{r.text}"
    except Exception as e:
        return False, str(e)

def send_alert_once(key, sym, title):
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < ALERT_COOLDOWN_SEC:
            return
        S["last_alert"][key] = time.time()
    send_signal_kakao(sym, title)

# ============================================================
# 토스 API
# ============================================================

def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        set_status("토스 키 없음")
        return ""
    try:
        r = requests.post(BASE + "/oauth2/token", data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, timeout=10)
        data = r.json() if r.text else {}
        if r.status_code != 200:
            set_status(f"토큰 오류 {r.status_code}")
            set_error(f"토큰 오류: {data}")
            return ""
        token = data.get("access_token", "")
        exp = int(data.get("expires_in", 3600))
        with LOCK:
            S["token"] = token
            S["token_exp"] = time.time() + max(60, exp - 300)
        set_status("토큰 정상")
        return token
    except Exception as e:
        set_error(f"토큰 예외: {e}")
        return ""

def ensure_token():
    with LOCK:
        token = S["token"]
        exp = S["token_exp"]
    if not token or time.time() >= exp:
        return get_token()
    return token

def auth_headers(account=False):
    token = ensure_token() or ""
    h = {"Authorization": "Bearer " + token}
    with LOCK:
        acc = S["account_seq"]
    if account and acc:
        h["X-Tossinvest-Account"] = str(acc)  # 계좌는 절대 int 변환 금지
    return h

def api_get(path, params=None, account=False, timeout=10):
    try:
        r = requests.get(BASE + path, headers=auth_headers(account), params=params or {}, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            set_error(f"GET {path} {r.status_code}: {str(data)[:300]}")
        return r.status_code, data
    except Exception as e:
        set_error(f"GET {path} 예외: {e}")
        return 0, {"error": str(e)}

def api_post(path, body=None, account=False, timeout=10):
    try:
        h = auth_headers(account)
        h["Content-Type"] = "application/json"
        r = requests.post(BASE + path, headers=h, json=body or {}, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            set_error(f"POST {path} {r.status_code}: {str(data)[:300]}")
        return r.status_code, data
    except Exception as e:
        set_error(f"POST {path} 예외: {e}")
        return 0, {"error": str(e)}

def first_list(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ["result", "accounts", "items", "data"]:
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ["accounts", "items", "list"]:
                if isinstance(v.get(k2), list):
                    return v[k2]
    return []

def amount_value(obj):
    if isinstance(obj, dict):
        for k in ["krw", "amount", "value", "cash", "marketValue"]:
            if k in obj:
                return amount_value(obj[k])
        return 0
    return to_float(obj)

def load_account_seq():
    code, data = api_get("/api/v1/accounts")
    if code != 200:
        set_status("계좌 목록 오류")
        return False
    accounts = first_list(data)
    if not accounts:
        set_status("계좌 없음")
        return False
    acc = accounts[0]
    account_seq = ""
    for key in ["accountSeq", "accountId", "accountNo", "accountNumber", "id", "number"]:
        if acc.get(key) not in [None, ""]:
            account_seq = str(acc.get(key))
            break
    with LOCK:
        S["account_seq"] = account_seq
        S["account_raw"] = acc
    return bool(account_seq)

def load_buying_power():
    code, data = api_get("/api/v1/buying-power", params={"currency": "KRW"}, account=True)
    if code != 200:
        return False
    result = data.get("result", data)
    cash = 0
    if isinstance(result, dict):
        for key in ["cashBuyingPower", "buyingPower", "availableAmount", "cash", "orderableAmount", "amount"]:
            if key in result:
                cash = amount_value(result[key])
                break
    with LOCK:
        S["cash"] = int(cash)
    return True

def load_holdings():
    code, data = api_get("/api/v1/holdings", account=True)
    if code != 200:
        return False
    result = data.get("result", data)
    if not isinstance(result, dict):
        return False
    total_market = amount_value(result.get("marketValue", 0))
    profit_loss = result.get("profitLoss", {})
    pl_amount = amount_value(profit_loss)
    pl_rate = to_float(profit_loss.get("rate", 0) if isinstance(profit_loss, dict) else 0)
    if abs(pl_rate) < 1:
        pl_rate *= 100
    holdings = []
    hold_qty = {}
    for item in result.get("items", []) or []:
        sym = str(item.get("symbol", ""))
        qty = to_float(item.get("quantity", item.get("qty", 0)))
        last_price = to_float(item.get("lastPrice", item.get("price", 0)))
        item_pl = item.get("profitLoss", {})
        pr = to_float(item_pl.get("rate", 0) if isinstance(item_pl, dict) else 0)
        if abs(pr) < 1:
            pr *= 100
        holdings.append({
            "symbol": sym,
            "name": item.get("name", name_of(sym)),
            "qty": qty,
            "last_price": last_price,
            "avg": to_float(item.get("averagePurchasePrice", item.get("avgPrice", 0))),
            "value": amount_value(item.get("marketValue", 0)) or qty * last_price,
            "pl_amt": amount_value(item_pl),
            "pl_rate": pr,
        })
        hold_qty[sym] = qty
    with LOCK:
        S["holdings"] = holdings
        S["hold_qty"] = hold_qty
        S["market_value"] = int(total_market)
        S["profit_loss"] = int(pl_amount)
        S["profit_rate"] = round(pl_rate, 2)
        S["total_value"] = int(S["cash"] + total_market)
        if S["real_base_cash"] <= 0 and S["total_value"] > 0:
            S["real_base_cash"] = S["total_value"]
    sync_real_watch_from_holdings()
    return True

def sync_real_watch_from_holdings():
    # 토스 보유종목을 기준으로 실계좌 보유감시 목록을 맞춤.
    # 밖에서 산 종목도 평균매수가가 있으면 자동으로 감시 대상에 들어감.
    with LOCK:
        holdings = list(S.get("holdings", []))
        prices = dict(S.get("prices", {}))
        watch = dict(S.get("real_watch", {}))
    active = set()
    for h in holdings:
        sym = str(h.get("symbol", ""))
        qty = to_float(h.get("qty", 0))
        if not sym or qty <= 0:
            continue
        active.add(sym)
        avg = to_float(h.get("avg", 0)) or to_float(h.get("last_price", 0)) or prices.get(sym, 0)
        cur = prices.get(sym, to_float(h.get("last_price", 0)) or avg)
        item = watch.get(sym, {}) if isinstance(watch.get(sym), dict) else {}
        # 실계좌는 토스 보유종목 평균매수가를 최우선으로 사용한다.
        # state.json에 예전 buy_price가 남아 있어도 실제 평균가로 덮어쓴다.
        old_buy = to_float(item.get("buy_price", 0))
        buy_price = avg or old_buy or cur
        high_after = max(to_float(item.get("high_after_buy", 0)), cur, buy_price)
        watch[sym] = {
            "symbol": sym,
            "name": name_of(sym),
            "qty": qty,
            "buy_price": buy_price,
            "buy_time": item.get("buy_time") or now_text(),
            "high_after_buy": high_after,
            "last_stage": item.get("last_stage", ""),
        }
    for sym in list(watch.keys()):
        if sym not in active:
            watch.pop(sym, None)
    with LOCK:
        S["real_watch"] = watch
    save_state()

def holding_thresholds():
    # 시장이 약하면 더 민감하게, 시장이 강하면 조금 더 넓게 본다.
    ms = S["market_score"].get("total", 50)
    if ms >= 65:
        return {"stop": -2.5, "protect_profit": 1.5, "trail_soft": -2.0, "trail_hard": -3.0, "score_warn": 45, "score_sell": 35}
    if ms >= 45:
        return {"stop": -2.0, "protect_profit": 1.0, "trail_soft": -1.5, "trail_hard": -2.5, "score_warn": 50, "score_sell": 40}
    return {"stop": -1.2, "protect_profit": 0.7, "trail_soft": -1.0, "trail_hard": -2.0, "score_warn": 55, "score_sell": 45}

def real_watch_detail(sym, item, stage):
    price = S["prices"].get(sym, 0)
    buy = to_float(item.get("buy_price", 0))
    high = to_float(item.get("high_after_buy", buy))
    profit = pct(price, buy) if buy else 0
    drop = pct(price, high) if high else 0
    sig = S["signals"].get(sym, {})
    return (
        f"매수가: {fmt_won(buy)}\n"
        f"매수 후 최고가: {fmt_won(high)}\n"
        f"현재 수익률: {profit:.2f}%\n"
        f"고점대비: {drop:.2f}%\n"
        f"AI 점수: {sig.get('score', 0)}\n"
        f"단계: {stage}"
    )

def check_real_holding_management():
    # 내가 실제로 산 종목을 계속 감시한다.
    # 매수가 대비 손실뿐 아니라, 올라갔다가 꺾이는 수익보호/익절 알림도 보낸다.
    with LOCK:
        watch = dict(S.get("real_watch", {}))
        prices = dict(S.get("prices", {}))
        signals = dict(S.get("signals", {}))
    if not watch:
        return
    th = holding_thresholds()
    changed = False
    for sym, item in watch.items():
        price = prices.get(sym, 0)
        buy = to_float(item.get("buy_price", 0))
        if price <= 0 or buy <= 0:
            continue
        old_high = to_float(item.get("high_after_buy", buy))
        high = max(old_high, price)
        if high != old_high:
            item["high_after_buy"] = high
            changed = True
        profit = pct(price, buy)
        drop_from_high = pct(price, high) if high else 0
        sig = signals.get(sym, {})
        score = to_float(sig.get("score", 50))
        stage = ""
        title = ""
        # 1) 손실 위험
        if profit <= th["stop"] or (score <= th["score_sell"] and profit < 0):
            stage = "LOSS_SELL"
            title = "⛔ 실계좌 보유 매도 후보"
        # 2) 수익권에서 고점 이탈: 먹고 빠지기/분할익절
        elif profit >= th["protect_profit"] and drop_from_high <= th["trail_hard"]:
            stage = "PROFIT_SELL"
            title = "💰 실계좌 수익보호 매도 후보"
        elif profit >= th["protect_profit"] and drop_from_high <= th["trail_soft"]:
            stage = "PROFIT_WARN"
            title = "💰 실계좌 익절/분할매도 검토"
        # 3) 아직 큰 손실은 아니어도 시장/점수 약화
        elif score <= th["score_warn"] and high_drop_pct(sym) <= -2:
            stage = "WEAK_WARN"
            title = "⚠️ 실계좌 보유 약화 경고"
        # 4) 반대 방향이 훨씬 강하면 교체 후보
        opp = INV if sym != INV else LEV
        opp_score = to_float(signals.get(opp, {}).get("score", 0))
        if opp_score >= 78 and opp_score >= score + 20:
            stage = "SWITCH"
            title = "🔁 실계좌 교체 후보"
        if not stage:
            continue
        key = f"REALWATCH_{sym}_{stage}"
        with LOCK:
            last = S["last_alert"].get(key, 0)
            if time.time() - last < HOLDING_ALERT_COOLDOWN_SEC:
                continue
            S["last_alert"][key] = time.time()
        detail = real_watch_detail(sym, item, stage)
        send_position_manage_alert(sym, title, detail)
    if changed:
        with LOCK:
            S["real_watch"] = watch
        save_state()

def load_sellable_quantities():
    with LOCK:
        targets = set(ALL.keys()) | set(S["hold_qty"].keys())
        holding_qty = dict(S["hold_qty"])
    sellable = {}
    for sym in targets:
        if not sym:
            continue

        # 토스 공식 문서의 Order 그룹: sellable quantity
        # endpoint는 /api/v1/sellable-quantity 를 사용한다.
        # /api/v1/sellable 은 404가 나와서 사용하지 않는다.
        code, data = api_get("/api/v1/sellable-quantity", params={"symbol": sym}, account=True, timeout=8)

        qty = 0
        if code == 200:
            r = data.get("result", data)
            if isinstance(r, dict):
                for k in ["sellableQuantity", "sellableQty", "quantity", "qty"]:
                    if k in r:
                        qty = to_float(r[k])
                        break
        else:
            # 매도가능수량 API가 응답하지 않으면 화면/버튼이 0으로 막히지 않도록
            # 보유수량을 임시 fallback으로 표시한다. 실제 주문은 토스 주문 API가 최종 검증한다.
            qty = holding_qty.get(sym, 0)

        sellable[sym] = qty
    with LOCK:
        S["sellable"] = sellable
    return True

def refresh_account_all():
    with LOCK:
        has_account = bool(S["account_seq"])
    if not has_account:
        load_account_seq()
    with LOCK:
        has_account = bool(S["account_seq"])
    if has_account:
        load_buying_power()
        load_holdings()
        load_sellable_quantities()

# ============================================================
# 가격 / 지표 / 뉴스
# ============================================================

def load_prices():
    code, data = api_get("/api/v1/prices", params={"symbols": ",".join(ALL.keys())}, timeout=15)
    if code != 200:
        set_status("현재가 오류")
        return False
    items = first_list(data)
    cnt = 0
    with LOCK:
        for item in items:
            sym = str(item.get("symbol", item.get("code", "")))
            price = 0
            for k in ["lastPrice", "price", "currentPrice", "closePrice", "tradePrice"]:
                if k in item:
                    price = to_float(item[k])
                    break
            if sym not in ALL or price <= 0:
                continue
            old = S["prices"].get(sym, price)
            S["prev_prices"][sym] = old
            S["prices"][sym] = price
            hist = S["history"].setdefault(sym, [])
            hist.append(price)
            if len(hist) > 240:
                del hist[:-240]
            S["high"][sym] = max(S["high"].get(sym, price), price)
            S["low"][sym] = min(S["low"].get(sym, price), price)
            cnt += 1
        S["updated"] = now_short()
        S["status"] = f"정상 ({cnt}/{len(ALL)})"
    return cnt > 0

def wma(values, n):
    if not values:
        return 0
    if len(values) < n:
        return values[-1]
    recent = values[-n:]
    weights = list(range(1, n + 1))
    return sum(v * w for v, w in zip(recent, weights)) / sum(weights)

def calc_wma_all():
    with LOCK:
        for sym in ALL:
            hist = S["history"].get(sym, [])
            p = S["prices"].get(sym, 0)
            if not hist and p:
                hist = [p]
            old = S["wma"].get(sym, {})
            S["wma"][sym] = {
                "wma5": round(wma(hist, 5), 2),
                "wma20": round(wma(hist, 20), 2),
                "wma60": round(wma(hist, 60), 2),
                "volume_ratio": old.get("volume_ratio", 1.0),
            }

def load_candles(sym, count=120):
    code, data = api_get("/api/v1/candles", params={"symbol": sym, "interval": "1m", "count": min(count, 200), "adjusted": "true"}, timeout=8)
    if code != 200:
        return False
    result = data.get("result", data)
    candles = result.get("candles", []) if isinstance(result, dict) else []
    closes = []
    vols = []
    for c in candles:
        closes.append(to_float(c.get("closePrice", c.get("close", 0))))
        vols.append(to_float(c.get("volume", 0)))
    closes = [x for x in closes if x > 0]
    if closes:
        v_recent = vols[-1] if vols else 0
        v_avg = sum(vols[-20:]) / len(vols[-20:]) if vols[-20:] else 0
        vr = (v_recent / v_avg) if v_avg > 0 else 1
        with LOCK:
            S["wma"][sym] = {"wma5": round(wma(closes, 5), 2), "wma20": round(wma(closes, 20), 2), "wma60": round(wma(closes, 60), 2), "volume_ratio": round(vr, 2)}
    return True

def refresh_candles(counter=0):
    targets = PRIMARY if counter % 3 else list(ALL.keys())
    for sym in targets:
        load_candles(sym)

def price_change_pct(sym):
    p = S["prices"].get(sym, 0)
    prev = S["prev_prices"].get(sym, p)
    return pct(p, prev)

def high_drop_pct(sym):
    p = S["prices"].get(sym, 0)
    h = S["high"].get(sym, p)
    return pct(p, h)

def low_rise_pct(sym):
    p = S["prices"].get(sym, 0)
    l = S["low"].get(sym, p)
    return pct(p, l)

def volume_ratio(sym):
    return S["wma"].get(sym, {}).get("volume_ratio", 1.0)

def fetch_google_news_titles(query, limit=5):
    try:
        url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
        r = requests.get(url, timeout=7)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        titles = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            if title:
                titles.append(title)
            if len(titles) >= limit:
                break
        return titles
    except Exception as e:
        set_error(f"뉴스 조회 오류: {e}")
        return []

def analyze_news_keywords():
    if not ENABLE_NEWS:
        return
    all_titles = []
    for q in NEWS_QUERIES:
        all_titles.extend(fetch_google_news_titles(q, limit=4))
    positives, negatives = [], []
    for title in all_titles:
        clean = title.strip()
        if any(kw.lower() in clean.lower() for kw in POSITIVE_NEWS_KEYWORDS):
            positives.append(clean)
        if any(kw.lower() in clean.lower() for kw in NEGATIVE_NEWS_KEYWORDS):
            negatives.append(clean)
    positives = list(dict.fromkeys(positives))[:8]
    negatives = list(dict.fromkeys(negatives))[:8]
    score = min(18, len(positives) * NEWS_SCORE_WEIGHT) - min(18, len(negatives) * NEWS_SCORE_WEIGHT)
    label = "뉴스 호재 우세" if score >= 10 else "뉴스 악재 우세" if score <= -10 else "뉴스 중립"
    with LOCK:
        S["news"] = {"updated": now_short(), "items": all_titles[:20], "score": score, "label": label, "positive": positives, "negative": negatives}

# ============================================================
# AI 점수 / 신호
# ============================================================

def raw_symbol_score(sym):
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return 0
    wm = S["wma"].get(sym, {})
    w5, w20, w60 = wm.get("wma5", 0), wm.get("wma20", 0), wm.get("wma60", 0)
    vr = wm.get("volume_ratio", 1)
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    lrise = low_rise_pct(sym)
    score = 50
    if w5 and price > w5:
        score += 10
    elif w5 and price < w5:
        score -= 10
    if w5 and w20 and w5 > w20:
        score += 12
    elif w5 and w20 and w5 < w20:
        score -= 12
    if w20 and w60 and w20 > w60:
        score += 6
    elif w20 and w60 and w20 < w60:
        score -= 6
    if chg > 0:
        score += 6
    elif chg < 0:
        score -= 6
    if vr >= 1.8 and chg > 0:
        score += 8
    elif vr >= 1.8 and chg < 0:
        score -= 10
    if hdrop <= -5:
        score -= 15
    elif hdrop <= -3:
        score -= 8
    if lrise >= 3 and chg > 0:
        score += 8
    return max(0, min(100, int(score)))

def calc_market_direction():
    kospi_base = raw_symbol_score("069500")
    kospi_lev = raw_symbol_score("122630")
    kospi_inv = raw_symbol_score("252670")
    kosdaq_base = raw_symbol_score("229200")
    kosdaq_lev = raw_symbol_score("233740")
    kosdaq_inv = raw_symbol_score("251340")
    kospi_score = int(((kospi_base + kospi_lev) / 2) - (kospi_inv - 50) * 0.4)
    kosdaq_score = int(((kosdaq_base + kosdaq_lev) / 2) - (kosdaq_inv - 50) * 0.4)
    total = int((kospi_score + kosdaq_score) / 2)
    label = "상승장" if total >= 65 else "하락장" if total <= 40 else "혼조/관망"
    with LOCK:
        S["market_score"] = {"kospi": max(0, min(100, kospi_score)), "kosdaq": max(0, min(100, kosdaq_score)), "total": max(0, min(100, total)), "label": label}

def calc_symbol_score(sym):
    score = raw_symbol_score(sym)
    if score <= 0:
        return 0
    news_score = S["news"].get("score", 0)
    market_total = S["market_score"].get("total", 50)
    is_inverse = "인버스" in name_of(sym)
    if is_inverse:
        score += int((50 - market_total) * 0.25)
        score -= int(news_score * 0.3)
    else:
        score += int((market_total - 50) * 0.25)
        score += int(news_score * 0.3)
    if sym == LEV:
        hynix_chg = price_change_pct(HYNIX)
        score += 8 if hynix_chg > 0 else -8 if hynix_chg < 0 else 0
    if sym == INV:
        hynix_chg = price_change_pct(HYNIX)
        score += 8 if hynix_chg < 0 else -8 if hynix_chg > 0 else 0
    return max(0, min(100, int(score)))

def bad_news_risk_detected(sym):
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    vr = volume_ratio(sym)
    news_score = S["news"].get("score", 0)
    return (chg <= -1.0 and hdrop <= -3.0 and vr >= 1.8) or (news_score <= -10 and hdrop <= -2.0)

def signal_label(sym, score):
    if bad_news_risk_detected(sym):
        return "악재성 급락 의심 ⚠️"
    if score >= 80:
        return "강한 진입 ⭕"
    if score >= 70:
        return "진입 후보 ⭕"
    if score >= 60:
        return "보유/관찰 🟡"
    if score >= 40:
        return "관망 🔴"
    if high_drop_pct(sym) <= -3 or volume_ratio(sym) >= 1.8:
        return "매도 후보 ⛔"
    return "약함 🔴"

def recommend_ratio(score):
    if score >= 85:
        return min(MAX_BUY_RATIO, 0.70)
    if score >= 75:
        return min(MAX_BUY_RATIO, 0.50)
    if score >= 65:
        return min(MAX_BUY_RATIO, 0.30)
    return 0.0

def build_signal(sym):
    price = S["prices"].get(sym, 0)
    score = S["scores"].get(sym, 0)
    ratio = recommend_ratio(score)
    qty = int((S["cash"] * ratio) // price) if price > 0 else 0
    sellable = int(S["sellable"].get(sym, 0))
    sell_qty = sellable if (score <= 40 or bad_news_risk_detected(sym)) else int(sellable * 0.5) if high_drop_pct(sym) <= -3 else 0
    return {
        "label": signal_label(sym, score),
        "score": score,
        "ratio": ratio,
        "qty": qty,
        "rec_buy_qty": qty,
        "rec_sell_qty": sell_qty,
        "hdrop": round(high_drop_pct(sym), 2),
        "lrise": round(low_rise_pct(sym), 2),
        "chg": round(price_change_pct(sym), 2),
        "volume_ratio": round(volume_ratio(sym), 2),
    }

def calc_scores():
    calc_market_direction()
    with LOCK:
        for sym in ALL:
            S["scores"][sym] = calc_symbol_score(sym)
        for sym in ALL:
            S["signals"][sym] = build_signal(sym)

def maybe_alert():
    if not is_market_watch_time():
        return
    with LOCK:
        signals = dict(S["signals"])
        prices = dict(S["prices"])
        prev_prices = dict(S["prev_prices"])
        watch = dict(S.get("real_watch", {}))
    now_h = now_kst().hour
    now_m = now_kst().minute
    is_morning = (now_h == 9 and now_m <= 30)  # 오전 9시~9시 30분 집중 구간

    for sym in ALERT_SYMBOLS:
        sig = signals.get(sym, {})
        score = sig.get("score", 0)
        price = prices.get(sym, 0)
        prev = prev_prices.get(sym, price)
        chg = pct(price, prev) if prev else 0
        vr = volume_ratio(sym)
        hdrop = high_drop_pct(sym)

        # 1) 악재성 급락 최우선
        if bad_news_risk_detected(sym):
            send_alert_once(f"RISK_{sym}", sym, "⚠️ 악재성 급락 의심")
            continue

        # 2) 눌림 진입 타이밍
        # 조건: 오전 9시~9시30분 + 점수 65이상 + 잠깐 -0.5% 이상 눌렸다가 거래량 살아있음
        if is_morning and score >= 65 and -2.0 <= chg <= -0.5 and vr >= 1.2:
            send_alert_once(f"PULLBACK_{sym}", sym, "📌 눌림 진입 타이밍!")
        # 오전 아니어도 점수 78이상이면 진입 알림
        elif score >= 78:
            send_alert_once(f"ENTRY_{sym}", sym, "🟢 AI 진입 후보")

        # 3) 보유 중인 종목 1%단위 알림
        if sym in watch:
            item = watch[sym]
            buy = to_float(item.get("buy_price", 0))
            if buy <= 0:
                continue
            profit = pct(price, buy)

            # 1% 단위로 알림 (정수 단위로 올림)
            import math
            profit_step = math.floor(profit)  # -2, -1, 0, 1, 2, 3 ...

            if profit_step >= 3:
                send_alert_once(f"TP3_{sym}_{profit_step}", sym, f"💰 +{profit_step}% 달성! 강하게 매도 검토")
            elif profit_step >= 2:
                send_alert_once(f"TP2_{sym}_{profit_step}", sym, f"💰 +{profit_step}% 달성 분할매도 검토")
            elif profit_step >= 1:
                send_alert_once(f"TP1_{sym}_{profit_step}", sym, f"📈 +{profit_step}% 수익 중")
            elif profit_step <= -2:
                send_alert_once(f"SL2_{sym}_{profit_step}", sym, f"🚨 {profit_step}% 손절 검토")
            elif profit_step <= -1:
                send_alert_once(f"SL1_{sym}_{profit_step}", sym, f"⚠️ {profit_step}% 손실 중 주의")

# ============================================================
# 실계좌 반자동 주문 / 가상매매
# ============================================================

def record_order(row):
    with LOCK:
        S["orders"].insert(0, row)
        S["orders"] = S["orders"][:80]
    write_row(orders_path(), ["time", "symbol", "name", "side", "qty", "status", "response"], row)

def place_order_manual(sym, side, qty):
    if sym not in ALL:
        return {"ok": False, "message": "허용되지 않은 종목"}
    if side not in ["BUY", "SELL"]:
        return {"ok": False, "message": "BUY/SELL 오류"}
    qty = to_int(qty)
    if qty <= 0:
        return {"ok": False, "message": "수량이 0입니다."}
    if side == "SELL":
        sellable = int(S["sellable"].get(sym, 0))
        if sellable <= 0:
            return {"ok": False, "message": "매도가능수량 0"}
        qty = min(qty, sellable)
    if not ENABLE_REAL_ORDER:
        row = {"time": now_short(), "symbol": sym, "name": name_of(sym), "side": "매수" if side == "BUY" else "매도", "qty": qty, "status": "차단", "response": "ENABLE_REAL_ORDER=false"}
        record_order(row)
        return {"ok": False, "message": "실계좌 주문이 비활성화되어 있습니다. ENABLE_REAL_ORDER=true 필요"}
    # Toss clientOrderId: 영문/숫자/하이픈/언더스코어, 최대 36자 제한에 맞춰 짧게 만든다.
    # 예: MW1720000000000A1B  (약 18자)
    client_order_id = f"MW{int(time.time() * 1000)}{uuid.uuid4().hex[:3].upper()}"
    body = {"clientOrderId": client_order_id, "symbol": sym, "side": side, "orderType": "MARKET", "quantity": str(qty)}
    code, data = api_post("/api/v1/orders", body=body, account=True, timeout=10)
    ok = code == 200
    side_kr = "매수" if side == "BUY" else "매도"
    row = {"time": now_short(), "symbol": sym, "name": name_of(sym), "side": side_kr, "qty": qty, "status": "성공" if ok else "실패", "response": json.dumps(data, ensure_ascii=False)[:500]}
    record_order(row)
    if ok:
        # 실제 버튼 주문이 성공하면 즉시 보유감시 목록에 반영한다.
        price = S["prices"].get(sym, 0)
        with LOCK:
            if side == "BUY":
                item = S["real_watch"].get(sym, {})
                buy_price = to_float(item.get("buy_price", 0)) or price
                old_qty = to_float(item.get("qty", 0))
                new_qty = old_qty + qty
                # 추가매수 시 평균가에 가깝게 갱신
                if old_qty > 0 and buy_price > 0 and price > 0:
                    buy_price = ((old_qty * buy_price) + (qty * price)) / new_qty
                S["real_watch"][sym] = {"symbol": sym, "name": name_of(sym), "qty": new_qty, "buy_price": buy_price, "buy_time": item.get("buy_time") or now_text(), "high_after_buy": max(to_float(item.get("high_after_buy", 0)), price, buy_price), "last_stage": ""}
            elif side == "SELL":
                item = S["real_watch"].get(sym, {})
                remain = to_float(item.get("qty", 0)) - qty
                if remain <= 0:
                    S["real_watch"].pop(sym, None)
                elif item:
                    item["qty"] = remain
                    S["real_watch"][sym] = item
        save_state()
    send_kakao(("✅" if ok else "⚠️") + f" 실계좌 반자동 {side_kr}\n{name_of(sym)}\n수량: {qty}주\n결과: {row['status']}", APP_URL)
    refresh_account_all()
    return {"ok": ok, "data": data, "message": row["status"]}

def paper_total_asset():
    with LOCK:
        total = S["paper"].get("cash", 0)
        positions = dict(S["paper"].get("positions", {}))
        prices = dict(S["prices"])
    for sym, pos in positions.items():
        total += to_float(pos.get("qty", 0)) * prices.get(sym, to_float(pos.get("avg", 0)))
    return int(total)

def update_paper_asset():
    with LOCK:
        asset = paper_total_asset()
        S["paper"]["asset"] = asset
        start = S["paper"].get("start_cash", 0)
        S["paper"]["profit_rate"] = pct(asset, start) if start else 0

def record_paper(action, sym, price, qty, reason, pl=0):
    update_paper_asset()
    with LOCK:
        row = {"time": now_short(), "action": action, "symbol": sym, "name": name_of(sym), "price": price, "qty": qty, "pl": pl, "reason": reason, "asset": S["paper"].get("asset", 0)}
        S["paper"]["trades"].insert(0, row)
        S["paper"]["trades"] = S["paper"]["trades"][:100]
    write_row(paper_path(), ["time", "action", "symbol", "name", "price", "qty", "pl", "reason", "asset"], row)
    save_state()

def paper_buy(sym, ratio, reason):
    if sym not in ALL:
        return False
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return False
    with LOCK:
        cash = S["paper"].get("cash", 0)
    qty = int((cash * ratio) // price)
    if qty <= 0:
        return False
    cost = qty * price
    with LOCK:
        pos = S["paper"]["positions"].get(sym, {"qty": 0, "avg": 0})
        old_qty = to_float(pos.get("qty", 0))
        old_avg = to_float(pos.get("avg", 0))
        new_qty = old_qty + qty
        new_avg = ((old_qty * old_avg) + cost) / new_qty if new_qty else price
        S["paper"]["cash"] -= cost
        S["paper"]["positions"][sym] = {"qty": new_qty, "avg": new_avg, "buy_time": now_text(), "high_after_buy": max(to_float(pos.get("high_after_buy", 0)), price, new_avg)}
        S["paper"]["last_action"] = f"{now_short()} 가상매수 {name_of(sym)}"
    record_paper("가상매수", sym, price, qty, reason)
    return True

def paper_sell(sym, ratio, reason):
    with LOCK:
        pos = S["paper"]["positions"].get(sym)
        price = S["prices"].get(sym, 0)
    if not pos or price <= 0:
        return False
    have = int(to_float(pos.get("qty", 0)))
    qty = have if ratio >= 1 else int(have * ratio)
    if qty <= 0:
        return False
    proceeds = qty * price
    avg = to_float(pos.get("avg", 0))
    pl = int((price - avg) * qty)
    with LOCK:
        S["paper"]["cash"] += proceeds
        S["paper"]["realized_pl"] += pl
        remain = have - qty
        if remain <= 0:
            S["paper"]["positions"].pop(sym, None)
        else:
            S["paper"]["positions"][sym] = {"qty": remain, "avg": avg, "buy_time": pos.get("buy_time", ""), "high_after_buy": pos.get("high_after_buy", avg)}
        S["paper"]["last_action"] = f"{now_short()} 가상매도 {name_of(sym)}"
    record_paper("가상매도", sym, price, qty, reason, pl)
    return True

def run_paper_ai_if_enabled():
    if not ENABLE_PAPER_AUTO:
        update_paper_asset()
        return
    # AI 가상 2천만원은 26개 후보 중에서 자동으로 매수/매도한다.
    with LOCK:
        positions = dict(S["paper"].get("positions", {}))
        signals = dict(S["signals"])
        prices = dict(S["prices"])
    th = holding_thresholds()
    for sym, pos in list(positions.items()):
        price = prices.get(sym, 0)
        avg = to_float(pos.get("avg", 0))
        if price <= 0 or avg <= 0:
            continue
        high = max(to_float(pos.get("high_after_buy", avg)), price)
        with LOCK:
            if sym in S["paper"]["positions"]:
                S["paper"]["positions"][sym]["high_after_buy"] = high
        profit = pct(price, avg)
        drop = pct(price, high) if high else 0
        sig = signals.get(sym, {})
        score = to_float(sig.get("score", 50))
        if profit <= th["stop"] or score <= th["score_sell"]:
            paper_sell(sym, 1.0, "AI 가상 자동 매도: 손실/점수 약화")
        elif profit >= th["protect_profit"] and drop <= th["trail_soft"]:
            paper_sell(sym, 0.5, "AI 가상 자동 분할익절: 수익권 고점 이탈")
        elif profit >= th["protect_profit"] and drop <= th["trail_hard"]:
            paper_sell(sym, 1.0, "AI 가상 자동 전량익절: 수익권 강한 고점 이탈")
    with LOCK:
        has = bool(S["paper"].get("positions"))
    if has:
        update_paper_asset()
        save_state()
        return
    # 26개 전체 중 점수 1등 후보. 단, 위험 신호는 제외.
    candidates = []
    for sym in ALL:
        sig = signals.get(sym, {})
        score = to_float(sig.get("score", 0))
        if score >= 78 and not bad_news_risk_detected(sym):
            candidates.append((score, sym))
    if candidates:
        candidates.sort(reverse=True)
        score, sym = candidates[0]
        paper_buy(sym, recommend_ratio(score), f"AI 가상 자동 진입: 26개 중 최고 후보 score={score}")
    update_paper_asset()
    save_state()

def reset_base_and_paper():
    refresh_account_all()
    with LOCK:
        total = S["total_value"]
    if total <= 0:
        return False, "총자산 조회 실패"
    with LOCK:
        S["real_base_cash"] = total
        # AI 가상계좌는 화면에서 2천만원 기준이 확실히 보이도록 고정 시작금 사용
        S["paper"] = {"start_cash": VIRTUAL_BASE_CASH, "cash": VIRTUAL_BASE_CASH, "positions": {}, "trades": [], "realized_pl": 0, "asset": VIRTUAL_BASE_CASH, "profit_rate": 0, "last_action": "2천만원 리셋"}
    save_state()
    send_kakao(f"🔄 기준금/AI가상 리셋\n실계좌 기준금: {fmt_won(total)}\nAI 가상 시작금: {fmt_won(VIRTUAL_BASE_CASH)}", APP_URL)
    return True, f"리셋 완료: 실계좌 {fmt_won(total)} / AI가상 {fmt_won(VIRTUAL_BASE_CASH)}"

# ============================================================
# 저장 / 루프
# ============================================================

def write_logs():
    hs = ["time", "symbol", "name", "price", "high", "low", "wma5", "wma20", "wma60", "volume_ratio", "score", "signal", "market_score", "market_label", "news_score", "news_label", "rec_buy_qty", "rec_sell_qty"]
    with LOCK:
        signals = dict(S["signals"])
        prices = dict(S["prices"])
        highs = dict(S["high"])
        lows = dict(S["low"])
        wmas = dict(S["wma"])
        market_score = dict(S["market_score"])
        news = dict(S["news"])
    for sym in ALL:
        price = prices.get(sym, 0)
        if price <= 0:
            continue
        wm = wmas.get(sym, {})
        sig = signals.get(sym, {})
        row = {
            "time": now_text(), "symbol": sym, "name": name_of(sym), "price": price,
            "high": highs.get(sym, price), "low": lows.get(sym, price),
            "wma5": wm.get("wma5", 0), "wma20": wm.get("wma20", 0), "wma60": wm.get("wma60", 0), "volume_ratio": wm.get("volume_ratio", 1),
            "score": sig.get("score", 0), "signal": sig.get("label", ""),
            "market_score": market_score.get("total", 0), "market_label": market_score.get("label", ""),
            "news_score": news.get("score", 0), "news_label": news.get("label", ""),
            "rec_buy_qty": sig.get("rec_buy_qty", 0), "rec_sell_qty": sig.get("rec_sell_qty", 0),
        }
        write_row(summary_path(), hs, row)
        write_row(symbol_path(sym), hs, row)
    write_portfolio_log()
    write_swing_decision_log()

def swing_decision_for_holding(sym, profit_rate, score, market_label, hdrop):
    # 실전 1차 안정화용: 매수 추천보다 보유/복구/매도 판단을 우선한다.
    if profit_rate <= -15:
        return "복구 모드", "신규매수 금지 / 추가매수 금지 / 반등 확인 대기"
    if profit_rate <= -5:
        return "손실 관리", "추가매수 금지 / 약세 지속 시 축소 검토"
    if score <= 40 or hdrop <= -3:
        return "매도 후보", "절반 축소 또는 전량 매도 검토"
    if score >= 60 and market_label != "하락장":
        return "스윙 보유", "보유 유지"
    return "관망", "현금 비중 유지 / 신규매수 금지"

def write_portfolio_log():
    headers = ["time", "symbol", "name", "qty", "avg", "last_price", "value", "pl_amt", "pl_rate", "cash", "total_value", "profit_loss", "profit_rate"]
    with LOCK:
        holdings = list(S.get("holdings", []))
        cash = S.get("cash", 0)
        total_value = S.get("total_value", 0)
        profit_loss = S.get("profit_loss", 0)
        profit_rate = S.get("profit_rate", 0)
    if not holdings:
        write_row(portfolio_path(), headers, {"time": now_text(), "symbol": "", "name": "보유없음", "cash": cash, "total_value": total_value, "profit_loss": profit_loss, "profit_rate": profit_rate})
        return
    for h in holdings:
        row = {"time": now_text(), "cash": cash, "total_value": total_value, "profit_loss": profit_loss, "profit_rate": profit_rate}
        row.update(h)
        write_row(portfolio_path(), headers, row)

def write_swing_decision_log():
    headers = ["time", "symbol", "name", "price", "qty", "avg", "real_profit_rate", "market_label", "market_score", "ai_score", "hdrop", "decision", "action", "reason"]
    with LOCK:
        holdings = list(S.get("holdings", []))
        prices = dict(S.get("prices", {}))
        signals = dict(S.get("signals", {}))
        market = dict(S.get("market_score", {}))
    for h in holdings:
        sym = str(h.get("symbol", ""))
        if not sym:
            continue
        price = prices.get(sym, to_float(h.get("last_price", 0)))
        avg = to_float(h.get("avg", 0))
        profit_rate = pct(price, avg) if avg else to_float(h.get("pl_rate", 0))
        sig = signals.get(sym, {})
        score = to_float(sig.get("score", 0))
        hdrop = high_drop_pct(sym)
        decision, action = swing_decision_for_holding(sym, profit_rate, score, market.get("label", ""), hdrop)
        reason = f"실계좌 평균가 기준, 시장={market.get('label','')}, AI={score}, 고점대비={hdrop:.2f}%"
        row = {
            "time": now_text(), "symbol": sym, "name": name_of(sym), "price": price,
            "qty": h.get("qty", 0), "avg": avg, "real_profit_rate": round(profit_rate, 2),
            "market_label": market.get("label", ""), "market_score": market.get("total", 0),
            "ai_score": score, "hdrop": round(hdrop, 2), "decision": decision, "action": action, "reason": reason,
        }
        write_row(swing_path(), headers, row)

def create_backup_zip():
    path = backup_zip_path()
    base = day_dir()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            for fn in files:
                fp = os.path.join(root, fn)
                if fp == path:
                    continue
                arc = os.path.relpath(fp, base)
                z.write(fp, arc)
    return path

def maybe_send_daily_backup():
    n = now_kst()
    if not (n.hour == 15 and 35 <= n.minute <= 39):
        return
    key = f"BACKUP_SENT_{today()}"
    with LOCK:
        if S["last_alert"].get(key):
            return
        S["last_alert"][key] = time.time()
    path = create_backup_zip()
    url = f"{APP_URL}/download_backup" if APP_URL else "/download_backup"
    caption = f"📦 오늘 데이터 백업 완료\n날짜: {today()}\n시간: {now_short()}\n다운로드 링크: {url}"
    ok, msg = send_telegram_file(path, caption)
    if not ok:
        send_telegram(caption + f"\n파일전송 실패: {msg}", [[telegram_button("백업 다운로드", url)]])

def loop():
    load_state()
    get_token()
    refresh_account_all()
    load_prices()
    calc_wma_all()
    analyze_news_keywords()
    calc_scores()
    counter = 0
    last_news = 0
    while True:
        try:
            # 1) 가격과 계좌를 같은 루프에서 30초마다 갱신
            load_prices()
            refresh_account_all()
            calc_wma_all()

            if counter % 2 == 0:
                try:
                    refresh_candles(counter)
                except Exception as e:
                    set_error(f"캔들 갱신 오류: {e}")

            if ENABLE_NEWS and time.time() - last_news >= NEWS_REFRESH_SEC:
                try:
                    analyze_news_keywords()
                    last_news = time.time()
                except Exception as e:
                    set_error(f"뉴스 갱신 오류: {e}")

            calc_scores()

            # 2) 저장은 알림보다 먼저. 알림 오류가 나도 데이터는 반드시 남긴다.
            write_logs()
            update_paper_asset()

            # 3) 알림/보유관리/가상매매는 각각 분리해서 하나가 터져도 루프 전체가 죽지 않게 한다.
            try:
                maybe_alert()
            except Exception as e:
                set_error(f"알림 오류: {e}")

            try:
                check_real_holding_management()
            except Exception as e:
                set_error(f"실계좌 보유관리 오류: {e}")

            try:
                run_paper_ai_if_enabled()
            except Exception as e:
                set_error(f"가상매매 오류: {e}")

            try:
                maybe_send_daily_backup()
            except Exception as e:
                set_error(f"백업 오류: {e}")

            ensure_token()
            counter += 1
        except Exception as e:
            set_error(f"루프 오류: {e}")
        time.sleep(max(10, REFRESH_SEC))

# ============================================================
# 웹 대시보드
# ============================================================

CSS = """
<style>
*{box-sizing:border-box}body{margin:0;padding:10px;background:#05060a;color:#f3f4f8;font-family:Arial,sans-serif;font-size:13px}h1{margin:6px 0 2px;text-align:center;color:#fff;font-size:22px}.sub{text-align:center;color:#777;font-size:11px;margin-bottom:10px}.grid{display:grid;grid-template-columns:1.05fr 1.5fr 1.1fr;gap:10px}.card{background:#11131c;border:1px solid #222635;border-radius:12px;padding:12px;margin-bottom:10px}.card h2{margin:0 0 8px;font-size:15px;color:#aaa}.big{font-size:25px;font-weight:bold}.mid{font-size:18px;font-weight:bold}.small{font-size:11px;color:#888}.red{color:#ff4d4d}.blue{color:#4d8cff}.green{color:#4dff88}.yellow{color:#ffd84d}.gray{color:#888}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#888;background:#161927;padding:6px;border-bottom:1px solid #252a3a}td{padding:6px;border-bottom:1px solid #1d2030}button{border:none;border-radius:7px;padding:8px 12px;margin:3px;font-weight:bold;cursor:pointer}.buy{background:#d71920;color:white}.sell{background:#1f64ff;color:white}.graybtn{background:#333;color:white}.gold{background:#ffd84d;color:black}.paperbtn{background:#7b3ff2;color:white}input{background:#05060a;color:white;border:1px solid #333;border-radius:6px;padding:7px;width:80px}.progress{width:100%;height:8px;background:#222;border-radius:10px;overflow:hidden;margin:6px 0}.bar{height:100%;background:#ffd84d}@media(max-width:900px){.grid{grid-template-columns:1fr}}
</style>
"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path == "/selfcheck":
            return self.json_response({
                "ok": True,
                "version": "SEMI_AUTO_HOLDING_MANAGEMENT",
                "symbols": len(ALL),
                "real_auto_buy": False,
                "real_auto_sell": False,
                "real_order_enabled": ENABLE_REAL_ORDER,
                "app_url": APP_URL,
                "telegram_configured": telegram_enabled(),
                "log_root": LOG_ROOT,
                "sellable_endpoint": "/api/v1/sellable-quantity",
                "real_holding_management": True,
                "paper_auto_26_symbols": ENABLE_PAPER_AUTO,
                "refresh_sec": REFRESH_SEC,
                "alert_symbols": ALERT_SYMBOLS,
                "backup_zip": backup_zip_path(),
            })
        if path == "/api":
            return self.json_response({k: S[k] for k in ["status", "updated", "cash", "total_value", "profit_loss", "profit_rate", "prices", "wma", "scores", "signals", "market_score", "news", "paper", "last_error"]})
        if path == "/refresh":
            load_prices(); refresh_candles(0); analyze_news_keywords(); calc_scores(); refresh_account_all(); update_paper_asset(); write_logs(); return self.redirect("/")
        if path == "/check_kakao":
            ok, msg = check_kakao(); return self.result_page("카카오 토큰 정상" if ok else "카카오 토큰 실패", msg)
        if path == "/check_telegram":
            ok, msg = check_telegram(); return self.result_page("텔레그램 봇 정상" if ok else "텔레그램 봇 실패", msg)
        if path == "/test_kakao":
            send_kakao("✅ 카카오 알림 테스트 성공\n" + now_text(), APP_URL); return self.result_page("카카오/텔레그램 테스트", "전송 요청 완료")
        if path == "/test_telegram":
            ok, msg = send_telegram_test(); return self.result_page("텔레그램 테스트", msg)
        if path == "/test_entry":
            send_signal_kakao(LEV, "🟢 테스트 레버리지 진입 후보"); return self.result_page("진입 알림 테스트", "카카오 버튼 알림 전송 요청 완료")
        if path == "/test_sell":
            send_signal_kakao(LEV, "⛔ 테스트 레버리지 매도 후보"); return self.result_page("매도 알림 테스트", "카카오 버튼 알림 전송 요청 완료")
        if path == "/confirm":
            return self.confirm_page(qs)
        if path == "/download_csv":
            return self.download_file(summary_path(), f"summary_{today()}.csv")
        if path == "/download_orders":
            return self.download_file(orders_path(), f"real_orders_{today()}.csv")
        if path == "/download_paper":
            return self.download_file(paper_path(), f"paper_trades_{today()}.csv")
        if path == "/download_portfolio":
            return self.download_file(portfolio_path(), f"portfolio_{today()}.csv")
        if path == "/download_swing":
            return self.download_file(swing_path(), f"swing_decision_{today()}.csv")
        if path == "/download_alert_log":
            return self.download_file(alert_log_path(), f"alert_log_{today()}.csv")
        if path == "/download_backup":
            path_zip = create_backup_zip()
            return self.download_file(path_zip, os.path.basename(path_zip), content_type="application/zip")
        if path == "/symbols_csv":
            return self.symbols_page()
        if path.startswith("/download_symbol/"):
            sym = path.split("/")[-1]
            return self.download_file(symbol_path(sym), os.path.basename(symbol_path(sym)))
        return self.render_dashboard()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        if path == "/order":
            return self.json_response(place_order_manual(str(body.get("symbol", "")), str(body.get("side", "")), body.get("qty", 0)))
        if path == "/paper_buy":
            return self.json_response({"ok": paper_buy(str(body.get("symbol", "")), to_float(body.get("ratio", 0.5)), "수동 가상매수")})
        if path == "/paper_sell":
            return self.json_response({"ok": paper_sell(str(body.get("symbol", "")), 1.0, "수동 가상매도")})
        if path == "/reset_base":
            ok, msg = reset_base_and_paper(); return self.json_response({"ok": ok, "message": msg})
        return self.json_response({"ok": False, "message": "unknown path"})

    def render_dashboard(self):
        html_doc = f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>80억 프로젝트 실전 반자동 관제센터</title><meta http-equiv="refresh" content="60">{CSS}</head><body>
<h1>80억 프로젝트 실전 반자동 관제센터</h1>
<div class="sub">업데이트 {safe(S['updated'])} | 상태 {safe(S['status'])} | 계좌 {safe(S['account_seq'])}</div>
<div class="grid"><div>{self.account_card()}{self.paper_card()}{self.holdings_card()}</div><div>{self.market_card()}{self.signal_card(LEV,'red')}{self.signal_card(INV,'blue')}{self.basic_card(HYNIX)}{self.stock_table()}</div><div>{self.test_card()}{self.news_card()}{self.alert_card()}{self.order_card()}{self.paper_trade_card()}</div></div>
<script>
async function postJson(path, body){{const res=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}})}});return await res.json();}}
async function order(symbol,side,qtyId){{const qty=document.getElementById(qtyId).value;const sideText=side==='BUY'?'매수':'매도';if(!qty||Number(qty)<=0){{alert('수량이 0입니다.');return;}}if(!confirm(symbol+' '+qty+'주 실계좌 '+sideText+' 주문 전송?'))return;const data=await postJson('/order',{{symbol:symbol,side:side,qty:qty}});alert(JSON.stringify(data));location.reload();}}
async function paperBuy(symbol){{const data=await postJson('/paper_buy',{{symbol:symbol,ratio:0.5}});alert(data.ok?'가상매수 완료':'가상매수 실패');location.reload();}}
async function paperSell(symbol){{const data=await postJson('/paper_sell',{{symbol:symbol}});alert(data.ok?'가상매도 완료':'가상매도 실패');location.reload();}}
async function resetBase(){{if(!confirm('현재 토스 총자산으로 기준금과 AI 가상계좌를 리셋할까요?'))return;const data=await postJson('/reset_base',{{}});alert(JSON.stringify(data));location.reload();}}
function setQty(id,qty){{document.getElementById(id).value=qty;}}
</script></body></html>"""
        self.html_response(html_doc)

    def account_card(self):
        real_rate = pct(S["total_value"], S["real_base_cash"]) if S["real_base_cash"] else 0
        return f"""<div class="card"><h2>실계좌</h2><div class="small">실제 기준금</div><div class="mid yellow">{fmt_won(S['real_base_cash'])}</div><br><div class="small">총자산</div><div class="big yellow">{fmt_won(S['total_value'])}</div><div class="small">기준금 대비 {real_rate:.2f}%</div><br><div class="small">매수가능금액</div><div class="mid">{fmt_won(S['cash'])}</div><br><div class="small">평가손익</div><div class="mid {color_class(S['profit_loss'])}">{fmt_won(S['profit_loss'])}</div><div class="{color_class(S['profit_rate'])}">{S['profit_rate']}%</div><br><div class="small">실주문 상태</div><div class="{'green' if ENABLE_REAL_ORDER else 'red'}">{'활성화' if ENABLE_REAL_ORDER else '비활성화'}</div><button class="gold" onclick="resetBase()">기준금/가상 리셋</button></div>"""

    def paper_card(self):
        p = S["paper"]
        update_paper_asset()
        pos_rows = ""
        positions = p.get("positions", {})
        if positions:
            for sym, pos in positions.items():
                cur = S["prices"].get(sym, 0)
                qty = to_float(pos.get("qty", 0))
                avg = to_float(pos.get("avg", 0))
                profit = (cur - avg) * qty
                pr = pct(cur, avg) if avg else 0
                pos_rows += f"{safe(name_of(sym))} {int(qty)}주 / 평손 <span class='{color_class(profit)}'>{fmt_won(profit)} {pr:.2f}%</span><br>"
        else:
            pos_rows = "없음"
        real_compare = pct(S["total_value"], S["real_base_cash"]) if S["real_base_cash"] else 0
        diff = p.get("profit_rate", 0) - real_compare
        return f"""<div class="card"><h2>AI 가상매매</h2><div class="small">가상 기준금</div><div class="big yellow">{fmt_won(VIRTUAL_BASE_CASH)}</div><div class="small">가상 시작금</div><div class="mid yellow">{fmt_won(p.get('start_cash',0))}</div><br><div class="small">가상 총자산</div><div class="big {color_class(p.get('asset',0)-p.get('start_cash',0))}">{fmt_won(p.get('asset',0))}</div><div class="{color_class(p.get('profit_rate',0))}">{p.get('profit_rate',0):.2f}%</div><br><div class="small">실제 대비 차이</div><div class="mid {color_class(diff)}">{diff:.2f}%p</div><br><div class="small">가상 보유</div><div>{pos_rows}</div><br><div class="small">마지막 행동</div><div>{safe(p.get('last_action','없음'))}</div><br><button class="paperbtn" onclick="paperBuy('{LEV}')">가상 레버 매수</button><button class="paperbtn" onclick="paperBuy('{INV}')">가상 인버스 매수</button><button class="sell" onclick="paperSell('{LEV}')">가상 레버 매도</button><button class="sell" onclick="paperSell('{INV}')">가상 인버스 매도</button></div>"""

    def holdings_card(self):
        rows = ""
        if not S["holdings"]:
            rows = "<tr><td colspan='4' class='gray'>보유 없음</td></tr>"
        else:
            for h in S["holdings"]:
                rows += f"<tr><td>{safe(h['name'])}<br><span class='small'>{safe(h['symbol'])}</span></td><td>{int(h['qty'])}주</td><td>{fmt_won(h['last_price'])}</td><td class='{color_class(h['pl_rate'])}'>{h['pl_rate']:.2f}%</td></tr>"
        return f"<div class='card'><h2>보유종목</h2><table><tr><th>종목</th><th>수량</th><th>현재가</th><th>수익률</th></tr>{rows}</table></div>"

    def market_card(self):
        ms = S["market_score"]
        return f"""<div class="card"><h2>시장 방향</h2><div class="big yellow">{safe(ms['label'])}</div><div class="small">종합 시장 점수 {ms['total']}</div><div class="progress"><div class="bar" style="width:{ms['total']}%"></div></div><table><tr><td>코스피 대용</td><td>{ms['kospi']}점</td></tr><tr><td>코스닥 대용</td><td>{ms['kosdaq']}점</td></tr><tr><td>KODEX 200</td><td>{fmt_won(S['prices'].get('069500',0))}</td></tr><tr><td>KODEX 레버리지</td><td>{fmt_won(S['prices'].get('122630',0))}</td></tr><tr><td>KODEX 인버스2X</td><td>{fmt_won(S['prices'].get('252670',0))}</td></tr></table></div>"""

    def real_watch_card(self):
        with LOCK:
            watch = dict(S.get("real_watch", {}))
        rows = ""
        for sym, item in watch.items():
            price = S["prices"].get(sym, 0)
            buy = to_float(item.get("buy_price", 0))
            high = to_float(item.get("high_after_buy", buy))
            profit = pct(price, buy) if buy else 0
            drop = pct(price, high) if high else 0
            rows += f"""<tr><td>{safe(name_of(sym))}<br><span class='small'>{sym}</span></td><td>{fmt_won(buy)}</td><td>{fmt_won(high)}</td><td class='{color_class(profit)}'>{profit:.2f}%</td><td class='{color_class(drop)}'>{drop:.2f}%</td></tr>"""
        if not rows:
            rows = "<tr><td colspan='5' class='gray'>실계좌 보유감시 없음</td></tr>"
        return f"""<div class='card'><h2>실계좌 보유관리</h2><div class='small'>내가 산 종목의 매수가와 매수 후 최고가를 기준으로 손절/익절/수익보호 알림</div><table><tr><th>종목</th><th>매수가</th><th>최고가</th><th>수익률</th><th>고점대비</th></tr>{rows}</table></div>"""

    def signal_card(self, sym, color):
        name = name_of(sym); price = S["prices"].get(sym, 0); score = S["scores"].get(sym, 0); sig = S["signals"].get(sym, {}); wm = S["wma"].get(sym, {}); sellable = int(S["sellable"].get(sym, 0)); rec_qty = int(sig.get("rec_buy_qty", 0)); rec_sell = int(sig.get("rec_sell_qty", 0)); ratio = int(sig.get("ratio", 0) * 100); qty_id = f"qty_{sym}"
        return f"""<div class="card"><h2>{safe(name)}</h2><div class="big {color}">{fmt_won(price)}</div><div class="small">신호</div><div class="mid">{safe(sig.get('label','-'))}</div><div class="small">AI 점수 {score}</div><div class="progress"><div class="bar" style="width:{score}%"></div></div><table><tr><td>WMA5</td><td>{fmt_won(wm.get('wma5',0))}</td></tr><tr><td>WMA20</td><td>{fmt_won(wm.get('wma20',0))}</td></tr><tr><td>WMA60</td><td>{fmt_won(wm.get('wma60',0))}</td></tr><tr><td>등락</td><td>{sig.get('chg',0)}%</td></tr><tr><td>거래량비율</td><td>{sig.get('volume_ratio',0)}배</td></tr><tr><td>고점대비</td><td>{sig.get('hdrop',0)}%</td></tr><tr><td>저점대비</td><td>{sig.get('lrise',0)}%</td></tr><tr><td>추천비중</td><td>{ratio}%</td></tr><tr><td>추천매수</td><td>{rec_qty}주</td></tr><tr><td>추천매도</td><td>{rec_sell}주</td></tr><tr><td>매도가능</td><td>{sellable}주</td></tr></table><div><input id="{qty_id}" type="number" value="{rec_qty}" min="0"><button class="buy" onclick="order('{sym}','BUY','{qty_id}')">실계좌 매수</button><button class="sell" onclick="order('{sym}','SELL','{qty_id}')">실계좌 매도</button><button class="graybtn" onclick="setQty('{qty_id}',{sellable})">전량</button></div></div>"""

    def basic_card(self, sym):
        price = S["prices"].get(sym, 0); chg = price_change_pct(sym); wm = S["wma"].get(sym, {})
        return f"<div class='card'><h2>{safe(name_of(sym))}</h2><div class='big'>{fmt_won(price)}</div><div class='small'>등락 {chg:.2f}%</div><table><tr><td>WMA5</td><td>{fmt_won(wm.get('wma5',0))}</td></tr><tr><td>WMA20</td><td>{fmt_won(wm.get('wma20',0))}</td></tr><tr><td>WMA60</td><td>{fmt_won(wm.get('wma60',0))}</td></tr><tr><td>거래량비율</td><td>{wm.get('volume_ratio',1)}배</td></tr></table></div>"

    def stock_table(self):
        rows = ""
        for sym, name in ALL.items():
            price = S["prices"].get(sym, 0); chg = price_change_pct(sym); hd = high_drop_pct(sym); sig = S["signals"].get(sym, {}); vr = volume_ratio(sym); qid = f"qty_all_{sym}"; rq = int(sig.get("rec_buy_qty", 0)); sellable = int(S["sellable"].get(sym, 0))
            rows += f"""<tr><td>{safe(name)}<br><span class='small'>{safe(sym)}</span></td><td>{fmt_won(price)}</td><td class='{color_class(chg)}'>{chg:.2f}%</td><td>{vr:.2f}배</td><td>{hd:.2f}%</td><td>{sig.get('score', S['scores'].get(sym,''))}</td><td>{rq}주</td><td>{sig.get('rec_sell_qty',0)}주</td><td><input id='{qid}' type='number' value='{rq}' min='0'><button class='buy' onclick="order('{sym}','BUY','{qid}')">매수</button><button class='sell' onclick="order('{sym}','SELL','{qid}')">매도</button><button class='graybtn' onclick="setQty('{qid}',{sellable})">전량</button></td></tr>"""
        return f"<div class='card'><h2>전체 26종목 실전 반자동</h2><table><tr><th>종목</th><th>현재가</th><th>등락</th><th>거래량</th><th>고점</th><th>점수</th><th>추천매수</th><th>추천매도</th><th>주문</th></tr>{rows}</table></div>"

    def news_card(self):
        news = S.get("news", {})
        rows = ""
        for t in news.get("positive", [])[:5]: rows += f"<tr><td class='red'>호재</td><td>{safe(t)}</td></tr>"
        for t in news.get("negative", [])[:5]: rows += f"<tr><td class='blue'>악재</td><td>{safe(t)}</td></tr>"
        if not rows: rows = "<tr><td colspan='2' class='gray'>뉴스 없음</td></tr>"
        return f"<div class='card'><h2>뉴스 키워드</h2><div class='mid yellow'>{safe(news.get('label','뉴스 대기'))}</div><div class='small'>뉴스 점수 {news.get('score',0)} / 업데이트 {safe(news.get('updated','없음'))}</div><br><table><tr><th>구분</th><th>제목</th></tr>{rows}</table></div>"

    def test_card(self):
        return """<div class="card"><h2>테스트</h2><button class="graybtn" onclick="location.href='/refresh'">새로고침</button><button class="graybtn" onclick="location.href='/selfcheck'">SELF CHECK</button><button class="graybtn" onclick="location.href='/check_kakao'">카카오 토큰</button><button class="graybtn" onclick="location.href='/test_kakao'">카카오/텔레 테스트</button><button class="graybtn" onclick="location.href='/check_telegram'">텔레그램 확인</button><button class="graybtn" onclick="location.href='/test_telegram'">텔레그램 테스트</button><button class="buy" onclick="location.href='/test_entry'">진입 알림 테스트</button><button class="sell" onclick="location.href='/test_sell'">매도 알림 테스트</button><button class="gold" onclick="location.href='/download_csv'">가격 CSV</button><button class="gold" onclick="location.href='/download_paper'">가상매매 CSV</button><button class="gold" onclick="location.href='/download_orders'">주문 CSV</button><button class="gold" onclick="location.href='/download_portfolio'">포트폴리오 CSV</button><button class="gold" onclick="location.href='/download_swing'">스윙판단 CSV</button><button class="gold" onclick="location.href='/download_alert_log'">알림로그 CSV</button><button class="gold" onclick="location.href='/symbols_csv'">종목별 CSV</button><button class="gold" onclick="location.href='/download_backup'">오늘 전체 ZIP</button></div>"""

    def alert_card(self):
        rows = "".join(f"<tr><td class='small'>{safe(a['time'])}</td><td>{safe(a['msg']).replace(chr(10),'<br>')}</td></tr>" for a in S["alerts"][:20]) or "<tr><td colspan='2' class='gray'>없음</td></tr>"
        return f"<div class='card'><h2>카카오 / 신호 기록</h2><table><tr><th>시간</th><th>내용</th></tr>{rows}</table><div class='small red'>{safe(S['last_error'])}</div></div>"

    def order_card(self):
        rows = "".join(f"<tr><td class='small'>{safe(o['time'])}</td><td>{safe(o['name'])} {safe(o['side'])} {safe(o['qty'])}주</td><td class='{ 'green' if o['status']=='성공' else 'red' }'>{safe(o['status'])}</td></tr>" for o in S["orders"][:20]) or "<tr><td colspan='3' class='gray'>없음</td></tr>"
        return f"<div class='card'><h2>실계좌 반자동 주문 기록</h2><table><tr><th>시간</th><th>주문</th><th>결과</th></tr>{rows}</table></div>"

    def paper_trade_card(self):
        trades = S["paper"].get("trades", [])
        rows = "".join(f"<tr><td class='small'>{safe(t['time'])}</td><td>{safe(t['action'])}</td><td>{safe(t['name'])} {safe(t['qty'])}주</td><td class='{color_class(t.get('pl',0))}'>{fmt_won(t.get('pl',0))}</td></tr>" for t in trades[:20]) or "<tr><td colspan='4' class='gray'>없음</td></tr>"
        return f"<div class='card'><h2>AI 가상매매 기록</h2><table><tr><th>시간</th><th>행동</th><th>종목</th><th>손익</th></tr>{rows}</table></div>"

    def confirm_page(self, qs):
        sym = (qs.get("symbol") or [""])[0]; side = (qs.get("side") or ["BUY"])[0]; qty = to_int((qs.get("qty") or [0])[0]); sig = S["signals"].get(sym, {}); price = S["prices"].get(sym, 0); qid = "confirm_qty"; side_kr = "매수" if side == "BUY" else "매도"
        body = f"""<html><head><meta charset='utf-8'>{CSS}</head><body><div class='card'><h1>실계좌 {side_kr} 확인</h1><h2>{safe(name_of(sym))}</h2><div class='big'>{fmt_won(price)}</div><p>AI 점수: {sig.get('score',0)} / 신호: {safe(sig.get('label','-'))}</p><p>추천매수: {sig.get('rec_buy_qty',0)}주 / 추천매도: {sig.get('rec_sell_qty',0)}주 / 매도가능: {int(S['sellable'].get(sym,0))}주</p><input id='{qid}' type='number' value='{qty}' min='0'><button class='{ 'buy' if side=='BUY' else 'sell' }' onclick="order('{sym}','{side}','{qid}')">실계좌 {side_kr} 최종 실행</button><button class='graybtn' onclick="location.href='/'">취소</button></div><script>async function postJson(path, body){{const res=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}})}});return await res.json();}}async function order(symbol,side,qtyId){{const qty=document.getElementById(qtyId).value;if(!qty||Number(qty)<=0){{alert('수량 0');return;}}if(!confirm('최종 주문 실행?'))return;const data=await postJson('/order',{{symbol:symbol,side:side,qty:qty}});alert(JSON.stringify(data));location.href='/';}}</script></body></html>"""
        self.html_response(body)

    def symbols_page(self):
        links = "".join(f"<li><a href='/download_symbol/{sym}'>{safe(name)} CSV</a></li>" for sym, name in ALL.items())
        self.html_response(f"<html><head><meta charset='utf-8'>{CSS}</head><body><div class='card'><h1>종목별 CSV</h1><ul>{links}</ul><a href='/'>돌아가기</a></div></body></html>")

    def result_page(self, title, msg):
        self.html_response(f"<html><head><meta charset='utf-8'>{CSS}</head><body><div class='card'><h1>{safe(title)}</h1><pre>{safe(msg)}</pre><a href='/'>돌아가기</a></div></body></html>")

    def download_file(self, path, filename, content_type="text/csv; charset=utf-8"):
        # Python http.server는 헤더를 latin-1로 인코딩한다.
        # 한글 filename을 그대로 넣으면 UnicodeEncodeError가 나므로 filename*로 UTF-8 처리한다.
        if not os.path.exists(path):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("아직 저장된 데이터가 없습니다.".encode("utf-8"))
            return

        encoded_filename = quote(filename)
        safe_filename = filename.encode("ascii", "ignore").decode("ascii")
        if not safe_filename or safe_filename in [".csv", ".zip"]:
            safe_filename = "download.csv" if filename.lower().endswith(".csv") else "download.zip"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded_filename}")
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def html_response(self, body):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body.encode("utf-8"))

    def json_response(self, data):
        self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def redirect(self, location):
        self.send_response(302); self.send_header("Location", location); self.end_headers()

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    print("80억 프로젝트 실전 반자동 관제센터 시작:", PORT)
    threading.Thread(target=loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
