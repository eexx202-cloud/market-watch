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
# - 실계좌: 자동매수 없음. 매수는 사용자 선택, 수익권 자동매도는 선택적으로 실행
# - 카카오: 매수/매도 확인 링크 포함
# - 26개 종목: 현재가/점수/추천수량/버튼/CSV 저장
# - AI 가상: ENABLE_PAPER_AUTO=true 이면 2천만원 기준 AI 자동매수/자동매도
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

# V4.24 기본 운용은 완전 가상실전이다. PAPER_ONLY_MODE=true이면
# Render 환경변수가 실수로 켜져 있어도 실제 주문 API를 호출하지 않는다.
PAPER_ONLY_MODE = os.environ.get("PAPER_ONLY_MODE", "true").lower() == "true"
ENABLE_REAL_ORDER = (os.environ.get("ENABLE_REAL_ORDER", "false").lower() == "true") and (not PAPER_ONLY_MODE)
ENABLE_NEWS = os.environ.get("ENABLE_NEWS", "true").lower() == "true"
ENABLE_PAPER_AUTO = os.environ.get("ENABLE_PAPER_AUTO", "true").lower() == "true"
NEWS_REFRESH_SEC = int(os.environ.get("NEWS_REFRESH_SEC", "600"))
REFRESH_SEC = int(os.environ.get("REFRESH_SEC", "30"))
NEWS_SCORE_WEIGHT = int(os.environ.get("NEWS_SCORE_WEIGHT", "6"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
MAX_BUY_RATIO = float(os.environ.get("MAX_BUY_RATIO", "0.70"))
VIRTUAL_BASE_CASH = int(float(os.environ.get("VIRTUAL_BASE_CASH", "10000000")))

# 70개 독립 가상계좌
# 1그룹 고정전략: RI01~RI15(삼성·하이닉스 포함), RE01~RE15(제외)
# 2그룹 순방향: WI01~WI15(삼성·하이닉스 포함), WE01~WE15(제외)
# 3그룹 전체시장: G01~G05 기존 방식 유지
# 추가 실험군: C01~C05 오전·오후 조합 전략
ENABLE_MULTI_PAPER_AI = os.environ.get("ENABLE_MULTI_PAPER_AI", "true").lower() == "true"
MULTI_AI_START_CASH = int(float(os.environ.get("MULTI_AI_START_CASH", "10000000")))
MULTI_AI_FEE_SIDE_PCT = float(os.environ.get("MULTI_AI_FEE_SIDE_PCT", "0.10"))
MULTI_AI_MAX_POSITION_RATIO = float(os.environ.get("MULTI_AI_MAX_POSITION_RATIO", "0.90"))
MULTI_AI_DECISION_COOLDOWN_SEC = int(os.environ.get("MULTI_AI_DECISION_COOLDOWN_SEC", "180"))

RESEARCH_BASE_NAMES = {
    1:"연구고정 오전추세",2:"연구고정 오전역추세",3:"연구고정 오전돌파",
    4:"연구고정 오전눌림",5:"연구고정 09:15",6:"연구고정 10:00",
    7:"연구고정 11:00",8:"연구고정 오후추세",9:"연구고정 오후역추세",
    10:"연구고정 오후돌파",11:"연구고정 2구간",12:"연구고정 저노출",
    13:"연구고정 관망강화",14:"연구고정 추적청산",15:"연구고정 오버나이트",
}
WALK_BASE_NAMES = {
    1:"순방향 누적수익 1위",2:"순방향 누적 상위3 분산",3:"순방향 최근3일 1위",
    4:"순방향 최근5일 1위",5:"순방향 최근7일 1위",6:"순방향 최근10일 1위",
    7:"순방향 최근5일 위험조정",8:"순방향 최근10일 위험조정",9:"순방향 최소MDD",
    10:"순방향 승률우선",11:"순방향 수익MDD 혼합",12:"순방향 50·30·20",
    13:"순방향 단기역추세",14:"순방향 지연추세",15:"순방향 현금관망",
}

MULTI_AI_IDS = (
    [f"RI{i:02d}" for i in range(1, 16)] +
    [f"RE{i:02d}" for i in range(1, 16)] +
    [f"WI{i:02d}" for i in range(1, 16)] +
    [f"WE{i:02d}" for i in range(1, 16)] +
    [f"G{i:02d}" for i in range(1, 6)] +
    [f"C{i:02d}" for i in range(1, 6)]
)

MULTI_AI_NAMES = {
    **{f"RI{i:02d}":f"1그룹 포함형 {RESEARCH_BASE_NAMES[i]}" for i in range(1,16)},
    **{f"RE{i:02d}":f"1그룹 제외형 {RESEARCH_BASE_NAMES[i]}" for i in range(1,16)},
    **{f"WI{i:02d}":f"2그룹 포함형 {WALK_BASE_NAMES[i]}" for i in range(1,16)},
    **{f"WE{i:02d}":f"2그룹 제외형 {WALK_BASE_NAMES[i]}" for i in range(1,16)},
    "G01":"전체시장 거래대금·돈몰림","G02":"전체시장 추세·돌파",
    "G03":"전체시장 눌림목·재상승","G04":"전체시장 급락·반전",
    "G05":"전체시장 종합자율",
    "C01":"조합 오전인버스→오후레버리지",
    "C02":"조합 오전인버스→오후인버스",
    "C03":"조합 11:30 방향전환",
    "C04":"조합 삼성·하이닉스 포함 자율",
    "C05":"조합 삼성·하이닉스 제외 자율",
}
MULTI_AI_GROUP = {
    **{f"RI{i:02d}":"RESEARCH_FIXED" for i in range(1,16)},
    **{f"RE{i:02d}":"RESEARCH_FIXED" for i in range(1,16)},
    **{f"WI{i:02d}":"WALK_FORWARD" for i in range(1,16)},
    **{f"WE{i:02d}":"WALK_FORWARD" for i in range(1,16)},
    **{f"G{i:02d}":"FULL_MARKET_LIVE" for i in range(1,6)},
    **{f"C{i:02d}":"INTRADAY_COMBO" for i in range(1,6)},
}
MULTI_AI_UNIVERSE = {
    **{f"RI{i:02d}":"INCLUDE_SAMSUNG_HYNIX" for i in range(1,16)},
    **{f"RE{i:02d}":"EXCLUDE_SAMSUNG_HYNIX" for i in range(1,16)},
    **{f"WI{i:02d}":"INCLUDE_SAMSUNG_HYNIX" for i in range(1,16)},
    **{f"WE{i:02d}":"EXCLUDE_SAMSUNG_HYNIX" for i in range(1,16)},
    **{f"G{i:02d}":"FULL_MARKET" for i in range(1,6)},
    "C01":"INCLUDE_SAMSUNG_HYNIX",
    "C02":"INCLUDE_SAMSUNG_HYNIX",
    "C03":"INCLUDE_SAMSUNG_HYNIX",
    "C04":"INCLUDE_SAMSUNG_HYNIX",
    "C05":"EXCLUDE_SAMSUNG_HYNIX",
}
MULTI_AI_PARENT = {
    **{f"RI{i:02d}":f"R{i:02d}" for i in range(1,16)},
    **{f"RE{i:02d}":f"R{i:02d}" for i in range(1,16)},
    **{f"WI{i:02d}":f"W{i:02d}" for i in range(1,16)},
    **{f"WE{i:02d}":f"W{i:02d}" for i in range(1,16)},
    **{f"G{i:02d}":f"G{i:02d}" for i in range(1,6)},
    **{f"C{i:02d}":f"C{i:02d}" for i in range(1,6)},
}

# 3그룹 전체시장 스캐너
ENABLE_FULL_MARKET_SCANNER = os.environ.get("ENABLE_FULL_MARKET_SCANNER", "true").lower() == "true"
FULL_MARKET_UNIVERSE_PATH = os.environ.get("FULL_MARKET_UNIVERSE_PATH", "kr_market_universe.csv")
FULL_MARKET_STOCK_MASTER_AUTOLOAD = os.environ.get("FULL_MARKET_STOCK_MASTER_AUTOLOAD", "true").lower() == "true"
FULL_MARKET_STOCK_MASTER_REFRESH_SEC = int(os.environ.get("FULL_MARKET_STOCK_MASTER_REFRESH_SEC", "21600"))
FULL_MARKET_STOCK_MASTER_CACHE_PATH = os.environ.get("FULL_MARKET_STOCK_MASTER_CACHE_PATH", "kr_market_universe_cache.json")
FULL_MARKET_SYMBOLS_ENV = os.environ.get("FULL_MARKET_SYMBOLS", "")
FULL_MARKET_BATCH_SIZE = int(os.environ.get("FULL_MARKET_BATCH_SIZE", "80"))
FULL_MARKET_SCAN_INTERVAL_SEC = int(os.environ.get("FULL_MARKET_SCAN_INTERVAL_SEC", "60"))
FULL_MARKET_TOP_N = int(os.environ.get("FULL_MARKET_TOP_N", "80"))
FULL_MARKET_RANKING_COUNT = int(os.environ.get("FULL_MARKET_RANKING_COUNT", "100"))
FULL_MARKET_RANKING_TYPES = [
    "MARKET_TRADING_AMOUNT",
    "MARKET_TRADING_VOLUME",
    "TOP_GAINERS",
    "TOP_LOSERS",
]
FULL_MARKET_MIN_PRICE = int(os.environ.get("FULL_MARKET_MIN_PRICE", "1000"))
FULL_MARKET_MIN_TURNOVER = float(os.environ.get("FULL_MARKET_MIN_TURNOVER", "1000000000"))
FULL_MARKET_BLOCKED_SYMBOLS_BASE = {
    "000660","005930","0193L0","0193T0","0193W0","0197X0"
}



# 공식 국내 장 캘린더 + 데이터 신선도 차단
ENABLE_MARKET_SAFETY_GATE = os.environ.get("ENABLE_MARKET_SAFETY_GATE", "true").lower() == "true"
MARKET_CALENDAR_REFRESH_SEC = int(os.environ.get("MARKET_CALENDAR_REFRESH_SEC", "1800"))
MAX_PRICE_AGE_SEC = int(os.environ.get("MAX_PRICE_AGE_SEC", "90"))
MAX_ORDERBOOK_AGE_SEC = int(os.environ.get("MAX_ORDERBOOK_AGE_SEC", "90"))
REQUIRE_FRESH_ORDERBOOK_FOR_SHADOW = os.environ.get("REQUIRE_FRESH_ORDERBOOK_FOR_SHADOW", "true").lower() == "true"
PROTECTED_REAL_SYMBOLS = {x.strip() for x in os.environ.get("PROTECTED_REAL_SYMBOLS", "0193W0").split(",") if x.strip()}
FULL_MARKET_BLOCKED_SYMBOLS = FULL_MARKET_BLOCKED_SYMBOLS_BASE | PROTECTED_REAL_SYMBOLS

# ============================================================
# V4.23 토스 공식 시장데이터 수집
# - 정식 1분봉 OHLCV
# - 호가/잔량
# - 최근 체결
# - KOSPI/KOSDAQ 지수와 투자자별 매매대금
# - 매매 판단에는 아직 강제 반영하지 않고 CSV 수집만 수행
# ============================================================
ENABLE_TOSS_MARKET_DATA_CAPTURE = os.environ.get("ENABLE_TOSS_MARKET_DATA_CAPTURE", "true").lower() == "true"
MARKET_DATA_CANDLE_SEC = int(os.environ.get("MARKET_DATA_CANDLE_SEC", "60"))
MARKET_DATA_ORDERFLOW_SEC = int(os.environ.get("MARKET_DATA_ORDERFLOW_SEC", "30"))
MARKET_DATA_INVESTOR_SEC = int(os.environ.get("MARKET_DATA_INVESTOR_SEC", "300"))
MARKET_DATA_CANDLE_COUNT = int(os.environ.get("MARKET_DATA_CANDLE_COUNT", "3"))
MARKET_DATA_TRADE_COUNT = int(os.environ.get("MARKET_DATA_TRADE_COUNT", "20"))
MARKET_DATA_CORE_SYMBOLS = [x.strip() for x in os.environ.get(
    "MARKET_DATA_CORE_SYMBOLS",
    "0197X0,122630,0193T0,252670,000660,005930,069500,229200"
).split(",") if x.strip()]
MARKET_DATA_ORDERFLOW_SYMBOLS = [x.strip() for x in os.environ.get(
    "MARKET_DATA_ORDERFLOW_SYMBOLS",
    "0197X0,122630,0193T0,252670"
).split(",") if x.strip()]
MARKET_DATA_FOCUS_WINDOWS = [
    ("09:00", "10:05"),
    ("11:35", "13:05"),
    ("14:45", "15:05"),
]
# ============================================================
# 구 구 단타 단타 엔진 제거
# - 실계좌는 V4.10 목표 패턴 알림만 사용
# - 과거 DAYTRADE 엔진/시드/리셋/실행 URL은 비활성화
# ============================================================
ENABLE_DAYTRADE = False
DAYTRADE_BASE_CASH = 0
DAYTRADE_STATE_PATH = os.environ.get("DAYTRADE_STATE_PATH", "daytrade_state.json")
DAYTRADE_EXEC_TOKEN = ""
DAYTRADE_MAX_TRADES = 0
DAYTRADE_TP_START = 1.0
DAYTRADE_TP_HARD = 3.0
DAYTRADE_STOP_LOSS = -2.0
DAYTRADE_TRAIL_DROP = 0.6
DAYTRADE_NO_ENTRY_AFTER = "14:30"
DAYTRADE_FORCE_EXIT_AFTER = "15:20"
DAYTRADE_CUTOFF = "15:20"
DAYTRADE_AUTO_FORCE_SELL = False
DAYTRADE_ALERT_COOLDOWN_SEC = 180
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

# V4.10 실계좌 판단 대상: 시장상황 핵심 종목
REAL_LONG_PRIORITY = [LEV, "494310", "0193W0", "122630", "233740"]
REAL_INVERSE_PRIORITY = [INV, "0193L0", "252670", "251340"]
REAL_TARGET_SYMBOLS = list(dict.fromkeys(REAL_LONG_PRIORITY + REAL_INVERSE_PRIORITY + [HYNIX, "005930", "069500", "229200"]))
ALERT_SYMBOLS = REAL_TARGET_SYMBOLS


# ============================================================
# OPERATING V4 최종 운영 규칙
# - 실계좌: 반자동. 사용자가 버튼을 눌러야 주문.
# - AI 가상계좌: ENABLE_PAPER_AUTO=true 이면 2천만원 기준 자동운영.
# ============================================================
OPERATING_VERSION = "OPERATING_V4_32_GROUP_SPLIT_PLUS_INTRADAY_COMBOS"

# 실전 실행 후보는 감시 26개 중 일부로 제한한다.
SEMI_LONG_SYMBOLS = [LEV, HYNIX, "494310", "488080", "469150", "122630", "069500", "0193W0", "005930"]
UP_LONG_SYMBOLS = [LEV, HYNIX, "494310", "488080", "122630", "069500", "0193W0", "005930"]
INVERSE_SYMBOLS = [INV, "252670", "0193L0", "251340"]
OBSERVE_ONLY_SYMBOLS = ["0100K0", "0080Y0", "462330", "0177X0", "445290", "433500", "487240", "418660", "465610", "225040", "0127R0"]

# 자금 운용 기준: 2,030만원 전후 계좌 기준
SWING_BUY_STEP_AMOUNTS = [7_000_000, 4_000_000, 4_000_000]
SWING_MAX_EXPOSURE = 15_000_000
MIN_DEFENSE_CASH = 5_000_000
INVERSE_MAX_EXPOSURE = 15_000_000
ORDER_SAFE_RATIO = 0.95

# 토스 API 요청 제한 방어: sellable-quantity는 보유종목만, 캐시 적용
SELLABLE_CACHE_SEC = int(os.environ.get("SELLABLE_CACHE_SEC", "180"))
SELLABLE_MIN_QTY = int(os.environ.get("SELLABLE_MIN_QTY", "2"))

# 시간 제한: 오늘 데이터 기준으로 확정
NO_BUY_BEFORE = os.environ.get("NO_BUY_BEFORE", "09:15")
NO_NEW_BUY_AFTER = "14:30"
DAYTRADE_FORCE_EXIT_TIME = "15:20"
# AI 가상계좌 자동운영 시간: 장중/정산 시간에만 작동한다.
# 장 마감 후에는 가상매수/가상매도/가상관망 로그를 새로 만들지 않는다.
PAPER_AUTO_START = os.environ.get("PAPER_AUTO_START", "09:00")
PAPER_AUTO_END = os.environ.get("PAPER_AUTO_END", "15:20")
PAPER_WAIT_LOG_COOLDOWN_SEC = int(os.environ.get("PAPER_WAIT_LOG_COOLDOWN_SEC", "600"))

# 실계좌 계좌조회 API 시간 제한: 장 마감 후 buying-power/holdings 반복조회 금지
# 데이터 저장은 계속하지만, 계좌/매수가능/보유/매도가능 조회는 이 시간 안에서만 자동 갱신한다.
ACCOUNT_REFRESH_START = os.environ.get("ACCOUNT_REFRESH_START", "08:50")
ACCOUNT_REFRESH_END = os.environ.get("ACCOUNT_REFRESH_END", "15:35")
INVALID_TOKEN_STATUS_COOLDOWN_SEC = int(os.environ.get("INVALID_TOKEN_STATUS_COOLDOWN_SEC", "300"))

# ============================================================
# V4.10 목표 패턴 설정
# - 리플레이/실시간/AI 가상/실계좌 알림이 같은 판단 함수를 사용하도록 통합
# ============================================================
TARGET_PATTERN_ENABLED = True
SCORE_BUY_DISABLED = True
LEGACY_DAYTRADE_REMOVED = True
TARGET_PATTERN_LOOKBACK_POINTS = int(os.environ.get("TARGET_PATTERN_LOOKBACK_POINTS", "600"))
TARGET_LONG_PULLBACK_PCT = float(os.environ.get("TARGET_LONG_PULLBACK_PCT", "8.0"))
TARGET_LONG_MAJOR_PULLBACK_PCT = float(os.environ.get("TARGET_LONG_MAJOR_PULLBACK_PCT", "10.0"))
TARGET_REBREAK_BUFFER_PCT = float(os.environ.get("TARGET_REBREAK_BUFFER_PCT", "0.15"))
TARGET_MAX_REAL_ALERTS_PER_DAY = int(os.environ.get("TARGET_MAX_REAL_ALERTS_PER_DAY", "4"))
TARGET_REAL_ALERT_COOLDOWN_SEC = int(os.environ.get("TARGET_REAL_ALERT_COOLDOWN_SEC", "600"))
TARGET_PAPER_MIN_HOLD_SEC = int(os.environ.get("TARGET_PAPER_MIN_HOLD_SEC", "900"))
TARGET_PAPER_REENTRY_COOLDOWN_SEC = int(os.environ.get("TARGET_PAPER_REENTRY_COOLDOWN_SEC", "900"))
TARGET_PAPER_MAX_TRADES_PER_DAY = int(os.environ.get("TARGET_PAPER_MAX_TRADES_PER_DAY", "8"))

# ============================================================
# V4.11 알림 정책
# - 실계좌 텔레그램 알림: 장중 스윙 단타 매수/매도만 전송
# - 짧은 단타: 알림 금지, CSV 기록만 남김
# - 텔레그램 주문 버튼: 30초 만료 + 현재가 재확인 + 가격괴리 차단
# ============================================================
REAL_ALERT_MODE = os.environ.get("REAL_ALERT_MODE", "WORK_SWING_ONLY")
ENABLE_WORK_SWING_ALERT = os.environ.get("ENABLE_WORK_SWING_ALERT", "true").lower() == "true"
ENABLE_FAST_SCALP_ALERT = os.environ.get("ENABLE_FAST_SCALP_ALERT", "false").lower() == "true"
ENABLE_FAST_SCALP_LOG_ONLY = os.environ.get("ENABLE_FAST_SCALP_LOG_ONLY", "true").lower() == "true"
ENABLE_TELEGRAM_BUTTON_ORDER = os.environ.get("ENABLE_TELEGRAM_BUTTON_ORDER", "true").lower() == "true"
TELEGRAM_BUTTON_TTL_SEC = int(os.environ.get("TELEGRAM_BUTTON_TTL_SEC", "90"))
MAX_BUTTON_PRICE_DRIFT_PCT = float(os.environ.get("MAX_BUTTON_PRICE_DRIFT_PCT", "0.5"))
TELEGRAM_NOTIFY_START = os.environ.get("TELEGRAM_NOTIFY_START", "08:50")
TELEGRAM_NOTIFY_END = os.environ.get("TELEGRAM_NOTIFY_END", "15:30")
FAST_SCALP_SCORE_MIN = int(os.environ.get("FAST_SCALP_SCORE_MIN", "85"))
FAST_SCALP_LOG_COOLDOWN_SEC = int(os.environ.get("FAST_SCALP_LOG_COOLDOWN_SEC", "60"))
WORK_SWING_MAX_REAL_ALERTS_PER_DAY = int(os.environ.get("WORK_SWING_MAX_REAL_ALERTS_PER_DAY", "4"))

# ============================================================
# V4.21 최종 최소 알림 정책
# - 현재 목적: 7월 고정전략 가상검증에 필요한 체결/손절/요약/백업만 수신
# - 예전 METHOD63/스윙 후보/보유 약화/뉴스·시장 후보 알림은 차단
# - 실계좌는 사용자가 버튼을 눌러 실제 주문한 결과와 실제 자동매도 결과만 알림
# ============================================================
FINAL_MINIMAL_ALERT_MODE = os.environ.get("FINAL_MINIMAL_ALERT_MODE", "true").lower() == "true"
ENABLE_METHOD63_CANDIDATE_ALERT = os.environ.get("ENABLE_METHOD63_CANDIDATE_ALERT", "false").lower() == "true"
ENABLE_REAL_PATTERN_CANDIDATE_ALERT = os.environ.get("ENABLE_REAL_PATTERN_CANDIDATE_ALERT", "false").lower() == "true"
ENABLE_HOLDING_WARNING_ALERT = os.environ.get("ENABLE_HOLDING_WARNING_ALERT", "false").lower() == "true"
ENABLE_GENERAL_SIGNAL_ALERT = os.environ.get("ENABLE_GENERAL_SIGNAL_ALERT", "false").lower() == "true"
ENABLE_SHADOW_TRADE_ALERT = os.environ.get("ENABLE_SHADOW_TRADE_ALERT", "true").lower() == "true"
ENABLE_SHADOW_DAILY_SUMMARY_ALERT = os.environ.get("ENABLE_SHADOW_DAILY_SUMMARY_ALERT", "true").lower() == "true"
ENABLE_REAL_ORDER_RESULT_ALERT = os.environ.get("ENABLE_REAL_ORDER_RESULT_ALERT", "true").lower() == "true"
ENABLE_REAL_AUTOSELL_RESULT_ALERT = os.environ.get("ENABLE_REAL_AUTOSELL_RESULT_ALERT", "true").lower() == "true"
ENABLE_DAILY_BACKUP_ALERT = os.environ.get("ENABLE_DAILY_BACKUP_ALERT", "true").lower() == "true"
ENABLE_KAKAO_MIRROR = os.environ.get("ENABLE_KAKAO_MIRROR", "false").lower() == "true"

# ============================================================
# V4.12 최종 수정: 회복 반등 + 수익권 자동매도
# - 자동매수는 계속 금지
# - 자동매도는 실전 허용 종목 + 수익권에서만 실행
# - 빨간색 추격이 아니라 VI/당일 저점 대비 살아나는 종목을 감지
# ============================================================
ENABLE_REAL_AUTO_BUY = os.environ.get("ENABLE_REAL_AUTO_BUY", "false").lower() == "true"
ENABLE_REAL_AUTO_SELL = os.environ.get("ENABLE_REAL_AUTO_SELL", "true").lower() == "true"
AUTO_SELL_PROFIT_ONLY = os.environ.get("AUTO_SELL_PROFIT_ONLY", "true").lower() == "true"
AUTO_SELL_LOSS_CUT = os.environ.get("AUTO_SELL_LOSS_CUT", "false").lower() == "true"
AUTO_SELL_MIN_PROFIT_PCT = float(os.environ.get("AUTO_SELL_MIN_PROFIT_PCT", "1.0"))
AUTO_SELL_PROFIT_START_PCT = float(os.environ.get("AUTO_SELL_PROFIT_START_PCT", "2.0"))
AUTO_SELL_TRAIL_DROP_PCT = float(os.environ.get("AUTO_SELL_TRAIL_DROP_PCT", "0.3"))
AUTO_SELL_BIG_PROFIT_PCT = float(os.environ.get("AUTO_SELL_BIG_PROFIT_PCT", "5.0"))
AUTO_SELL_BIG_TRAIL_DROP_PCT = float(os.environ.get("AUTO_SELL_BIG_TRAIL_DROP_PCT", "2.0"))
AUTO_SELL_FORCE_EXIT_TIME = os.environ.get("AUTO_SELL_FORCE_EXIT_TIME", "15:15")
AUTO_SELL_FORCE_EXIT_ONLY_PROFIT = os.environ.get("AUTO_SELL_FORCE_EXIT_ONLY_PROFIT", "true").lower() == "true"
RECOVERY_CANDIDATE_ENGINE = os.environ.get("RECOVERY_CANDIDATE_ENGINE", "true").lower() == "true"
POSITION_SET_REENTRY = os.environ.get("POSITION_SET_REENTRY", "true").lower() == "true"
FAMILY_MODE_ENGINE = os.environ.get("FAMILY_MODE_ENGINE", "true").lower() == "true"
PEAK_PROFIT_TRAILING_AUTO_SELL = os.environ.get("PEAK_PROFIT_TRAILING_AUTO_SELL", "true").lower() == "true"
ALERT_ONLY_ACTIONABLE = os.environ.get("ALERT_ONLY_ACTIONABLE", "true").lower() == "true"
VI_AFTER_RECHECK = os.environ.get("VI_AFTER_RECHECK", "true").lower() == "true"
RECOVERY_LOW_RISE_PCT = float(os.environ.get("RECOVERY_LOW_RISE_PCT", "3.0"))
RECOVERY_STRONG_LOW_RISE_PCT = float(os.environ.get("RECOVERY_STRONG_LOW_RISE_PCT", "5.0"))
RECOVERY_RECENT_UP_PCT = float(os.environ.get("RECOVERY_RECENT_UP_PCT", "0.25"))

# ============================================================
# V4.13 METHOD 63 하이닉스 전용 엔진
# - 6/24~7/2 리플레이 기준 최우선 후보
# - 실계좌 자동매수 OFF 유지
# - 매수는 사용자 판단, 매도는 자동매도
# ============================================================
METHOD63_HYNIX_ENGINE = os.environ.get("METHOD63_HYNIX_ENGINE", "true").lower() == "true"
METHOD63_HYNIX_ONLY = os.environ.get("METHOD63_HYNIX_ONLY", "true").lower() == "true"

METHOD63_START_TIME = os.environ.get("METHOD63_START_TIME", "09:15")
METHOD63_NO_NEW_BUY_AFTER = os.environ.get("METHOD63_NO_NEW_BUY_AFTER", "14:30")

METHOD63_MAX_SETS_PER_DAY = int(os.environ.get("METHOD63_MAX_SETS_PER_DAY", "2"))
METHOD63_SAME_DIRECTION_REENTRY = os.environ.get("METHOD63_SAME_DIRECTION_REENTRY", "false").lower() == "true"
METHOD63_REVERSE_WAIT_SEC = int(os.environ.get("METHOD63_REVERSE_WAIT_SEC", "600"))

METHOD63_INV_LOW_RISE_PCT = float(os.environ.get("METHOD63_INV_LOW_RISE_PCT", "3.0"))
METHOD63_LEV_LOW_RISE_PCT = float(os.environ.get("METHOD63_LEV_LOW_RISE_PCT", "7.0"))
METHOD63_OPPOSITE_WEAK_PCT = float(os.environ.get("METHOD63_OPPOSITE_WEAK_PCT", "1.0"))
METHOD63_RECENT_UP_PCT = float(os.environ.get("METHOD63_RECENT_UP_PCT", "0.1"))
METHOD63_RECENT_POINTS = int(os.environ.get("METHOD63_RECENT_POINTS", "10"))
METHOD63_ALERT_COOLDOWN_SEC = int(os.environ.get("METHOD63_ALERT_COOLDOWN_SEC", "300"))

BREAKEVEN_GUARD_AUTO_SELL = os.environ.get("BREAKEVEN_GUARD_AUTO_SELL", "true").lower() == "true"
BREAKEVEN_GUARD_TRIGGER_PCT = float(os.environ.get("BREAKEVEN_GUARD_TRIGGER_PCT", "2.0"))
BREAKEVEN_GUARD_EXIT_PCT = float(os.environ.get("BREAKEVEN_GUARD_EXIT_PCT", "0.3"))


# ============================================================
# SHADOW FIXED V1 실전가정 가상체결
# - 실계좌 주문을 절대 호출하지 않는 독립 가상계좌
# - 6/24~7/10 분석에서 확정한 고정시간 조합 규칙을 그대로 검증
# - 검증기간에는 아래 조건값을 바꾸지 않는다.
# ============================================================
SHADOW_FIXED_ENABLED = os.environ.get("SHADOW_FIXED_ENABLED", "true").lower() == "true"
SHADOW_FIXED_START_CASH = int(float(os.environ.get("SHADOW_FIXED_START_CASH", "10000000")))
SHADOW_FIXED_NOTIFY = os.environ.get("SHADOW_FIXED_NOTIFY", "true").lower() == "true"

# V4.19 균형형 고정전략
# 오전: 하이닉스 인버스(0197X0), 오후: KODEX 레버리지(122630)
# 실계좌 주문 함수는 절대 호출하지 않는 독립 가상계좌다.
SHADOW_FIXED_STRATEGY_ID = "HYNIX_INV_KODEX_LEV_BALANCED_V1"
SHADOW_INV_SYMBOL = "0197X0"
SHADOW_LEV_SYMBOL = "122630"
SHADOW_STOP_LOSS_PCT = float(os.environ.get("SHADOW_STOP_LOSS_PCT", "3.0"))
# 백테스트의 왕복비용 0.20%와 맞추기 위한 편도 비용 기본값 0.10%
SHADOW_FEE_SIDE_PCT = float(os.environ.get("SHADOW_FEE_SIDE_PCT", "0.10"))

# 오전 인버스: 09:15~09:45 등락률 범위, 09:46 체결
SHADOW_INV_BASE_TIME = "09:15"
SHADOW_INV_SIGNAL_TIME = "09:45"
SHADOW_INV_ENTRY_TIME = "09:46"
SHADOW_INV_EXIT_TIME = "14:00"
SHADOW_INV_MOVE_MIN_PCT = float(os.environ.get("SHADOW_INV_MOVE_MIN_PCT", "-5.0"))
SHADOW_INV_MOVE_MAX_PCT = float(os.environ.get("SHADOW_INV_MOVE_MAX_PCT", "6.0"))

# 오후 KODEX 레버리지: 11:45~12:45 등락률 범위, 12:46 체결, 15:00 청산
SHADOW_LEV_BASE_TIME = "11:45"
SHADOW_LEV_SIGNAL_TIME = "12:45"
SHADOW_LEV_ENTRY_TIME = "12:46"
SHADOW_LEV_EXIT_TIME = "15:00"
SHADOW_LEV_MOVE_MIN_PCT = float(os.environ.get("SHADOW_LEV_MOVE_MIN_PCT", "-4.0"))
SHADOW_LEV_MOVE_MAX_PCT = float(os.environ.get("SHADOW_LEV_MOVE_MAX_PCT", "0.0"))


# 실제 매수/매도 실행 후보. 나머지 종목은 판단/기록 참고용.
TRADE_ALLOWED_SYMBOLS = ["0193L0", "0193T0", "0197X0", "122630", "252670", "233740", "251340", "069500", "229200", "494310", "488080", "469150", "005930", "000660"]
# 실계좌 삼성전자 레버리지는 장기 복구 포지션: 손실권 자동매도/자동손절 절대 금지, 수익권에서만 매도 가능
REAL_PROFIT_ONLY_SYMBOLS = set()
# 완전 보호: 자동/수동 주문 모두 차단. 복구 관찰만 한다.
REAL_ORDER_BLOCKED_SYMBOLS = set(PROTECTED_REAL_SYMBOLS)
# 신규 매수 버튼/매수 알림은 하이닉스 레버리지/인버스만 허용한다.
# 기존 보유종목 자동매도는 TRADE_ALLOWED_SYMBOLS 기준으로 계속 보호한다.
HYNIX_TRADE_SYMBOLS = {LEV, INV}
FAST_SCALP_ALLOWED_SYMBOLS = TRADE_ALLOWED_SYMBOLS
WORK_SWING_ALLOWED_SYMBOLS = TRADE_ALLOWED_SYMBOLS




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
    "sellable_cache": {},
    "alerts": [],
    "last_alert": {},
    "orders": [],
    "pending_orders": {},
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
    "paper_ais": {},
    "full_market": {
        "universe": {},
        "quotes": {},
        "ranked": [],
        "cursor": 0,
        "last_scan_ts": 0,
        "last_scan_text": "없음",
        "stock_master_checked_at": 0,
        "stock_master_source": "없음",
        "status": "대기",
        "errors": 0,
    },
    "shadow_fixed": {
        "date": "",
        "strategy_id": SHADOW_FIXED_STRATEGY_ID,
        "start_cash": SHADOW_FIXED_START_CASH,
        "cash": SHADOW_FIXED_START_CASH,
        "position": None,
        "realized_pl": 0,
        "asset": SHADOW_FIXED_START_CASH,
        "profit_rate": 0,
        "checkpoints": {},
        "inv_evaluated": False,
        "lev_evaluated": False,
        "inv_signal": False,
        "lev_signal": False,
        "stopped_today": False,
        "summary_saved": False,
        "last_action": "초기화",
        "trades": [],
    },
    "daytrade": {
        "date": "",
        "cash": 0,
        "trade_count": 0,
        "position": None,
        "market_mode": "LEGACY_REMOVED",
        "pending": None,
        "trades": [],
        "last_action": "구 구 단타 단타 제거",
    },
    "target_pattern": {
        "date": "",
        "sent_count": 0,
        "stages": {},
        "last_choice": {},
        "last_action": "없음",
    },
    "market_data_capture": {
        "last_candle_ts": 0,
        "last_orderflow_ts": 0,
        "last_investor_ts": 0,
        "last_candle_minute": {},
        "last_trade_timestamp": {},
        "last_orderbook_timestamp": {},
        "latest_orderbook": {},
        "latest_trade": {},
        "price_timestamp": {},
        "calendar": {},
        "calendar_checked_at": 0,
        "gate_ok": False,
        "gate_reason": "NOT_CHECKED",
        "status": "대기",
        "errors": 0,
    },
    "method63": {
        "date": "",
        "set_count": 0,
        "last_side": "",
        "last_exit_ts": 0,
        "last_alert_ts": {},
        "last_action": "없음",
    },
}

# ============================================================
# 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)

def is_weekend_kst():
    """토요일(5), 일요일(6)이면 True."""
    return now_kst().weekday() >= 5

def today():
    return now_kst().strftime("%Y-%m-%d")

def now_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")

def now_short():
    return now_kst().strftime("%H:%M:%S")

def parse_api_datetime(value):
    """토스 ISO 8601 시각을 KST aware datetime으로 변환한다."""
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        return dt.astimezone(KST)
    except Exception:
        return None

def data_age_seconds(value):
    dt = parse_api_datetime(value)
    if dt is None:
        return 10**9
    return max(0.0, (now_kst() - dt).total_seconds())

def safe(v):
    return html.escape(str(v))

def name_of(sym):
    if sym in ALL:
        return ALL.get(sym, sym)
    q = S.get("full_market", {}).get("quotes", {}).get(sym, {})
    return str(q.get("name") or sym)

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

def refresh_kr_market_calendar(force=False):
    """공식 /api/v1/market-calendar/KR로 오늘 영업일과 정규장 시간을 캐시한다."""
    state = S.setdefault("market_data_capture", {})
    if (not force) and time.time() - to_float(state.get("calendar_checked_at", 0)) < MARKET_CALENDAR_REFRESH_SEC:
        return bool(state.get("calendar"))
    code, data = api_get("/api/v1/market-calendar/KR", params={"date": today()}, timeout=8)
    state["calendar_checked_at"] = time.time()
    if code != 200:
        state["calendar"] = {}
        state["gate_ok"] = False
        state["gate_reason"] = f"CALENDAR_HTTP_{code}"
        return False
    result = _result_dict(data)
    today_info = result.get("today", {}) if isinstance(result, dict) else {}
    integrated = today_info.get("integrated") if isinstance(today_info, dict) else None
    regular = integrated.get("regularMarket") if isinstance(integrated, dict) else None
    state["calendar"] = {
        "date": str(today_info.get("date", "")) if isinstance(today_info, dict) else "",
        "is_business_day": bool(regular),
        "regular_start": str(regular.get("startTime", "")) if isinstance(regular, dict) else "",
        "regular_end": str(regular.get("endTime", "")) if isinstance(regular, dict) else "",
        "auction_start": str(regular.get("singlePriceAuctionStartTime", "")) if isinstance(regular, dict) else "",
    }
    return True

def regular_market_open_now():
    state = S.setdefault("market_data_capture", {})
    refresh_kr_market_calendar(False)
    cal = state.get("calendar", {})
    if not cal or cal.get("date") != today():
        return False, "CALENDAR_NOT_TODAY"
    if not cal.get("is_business_day"):
        return False, "MARKET_CLOSED"
    start = parse_api_datetime(cal.get("regular_start"))
    end = parse_api_datetime(cal.get("regular_end"))
    if not start or not end:
        return False, "REGULAR_SESSION_MISSING"
    n = now_kst()
    if not (start <= n <= end):
        return False, "OUTSIDE_REGULAR_SESSION"
    return True, "OK"

def market_safety_gate(require_orderbook_symbol=None):
    """가상/실거래 공통 차단. 휴장, 장외, 과거 가격, 오래된 호가를 거부한다."""
    if not ENABLE_MARKET_SAFETY_GATE:
        return True, "GATE_DISABLED"
    state = S.setdefault("market_data_capture", {})
    ok, reason = regular_market_open_now()
    if not ok:
        state["gate_ok"], state["gate_reason"] = False, reason
        return False, reason
    price_ts = state.get("price_timestamp", {})
    check_symbols = [require_orderbook_symbol] if require_orderbook_symbol else MARKET_DATA_CORE_SYMBOLS[:2]
    ages = [data_age_seconds(price_ts.get(sym)) for sym in check_symbols if sym]
    if not ages or min(ages) > MAX_PRICE_AGE_SEC:
        reason = "STALE_PRICE"
        state["gate_ok"], state["gate_reason"] = False, reason
        return False, reason
    if require_orderbook_symbol and REQUIRE_FRESH_ORDERBOOK_FOR_SHADOW:
        ob = state.get("latest_orderbook", {}).get(require_orderbook_symbol, {})
        if data_age_seconds(ob.get("timestamp")) > MAX_ORDERBOOK_AGE_SEC:
            reason = "STALE_ORDERBOOK"
            state["gate_ok"], state["gate_reason"] = False, reason
            return False, reason
        if to_float(ob.get("best_ask", 0)) <= 0 or to_float(ob.get("best_bid", 0)) <= 0:
            reason = "INVALID_ORDERBOOK"
            state["gate_ok"], state["gate_reason"] = False, reason
            return False, reason
    state["gate_ok"], state["gate_reason"] = True, "OK"
    return True, "OK"

def is_market_watch_time():
    ok, _ = regular_market_open_now() if ENABLE_MARKET_SAFETY_GATE else (True, "")
    return ok

def account_api_time_open():
    # 장 마감 후에는 buying-power/holdings/sellable 반복조회 금지.
    # 가격/CSV 저장은 별도 루프에서 계속 유지한다.
    sh, sm = parse_hhmm(ACCOUNT_REFRESH_START, 8, 50)
    eh, em = parse_hhmm(ACCOUNT_REFRESH_END, 15, 35)
    n = now_kst()
    cur = (n.hour, n.minute)
    return (sh, sm) <= cur <= (eh, em)

def set_status_once(key, msg, cooldown=300):
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < cooldown:
            return
        S["last_alert"][key] = time.time()
    set_status(msg)

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

def fast_scalp_path():
    return os.path.join(day_dir(), f"fast_scalp_signals_{today()}.csv")


def shadow_fixed_path():
    return os.path.join(day_dir(), f"shadow_fixed_trades_{today()}.csv")

def shadow_fixed_signal_path():
    return os.path.join(day_dir(), f"shadow_fixed_signals_{today()}.csv")

def shadow_fixed_summary_path():
    return os.path.join(day_dir(), f"shadow_fixed_summary_{today()}.csv")

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

def market_data_dir():
    path = os.path.join(day_dir(), "market_data")
    os.makedirs(path, exist_ok=True)
    return path

def candle_1m_path(sym):
    return os.path.join(market_data_dir(), f"candles_1m_{sym}_{today()}.csv")

def orderbook_path(sym):
    return os.path.join(market_data_dir(), f"orderbook_{sym}_{today()}.csv")

def trades_path(sym):
    return os.path.join(market_data_dir(), f"trades_{sym}_{today()}.csv")

def market_indicator_path():
    return os.path.join(market_data_dir(), f"market_indicators_{today()}.csv")

def investor_trading_path():
    return os.path.join(market_data_dir(), f"investor_trading_{today()}.csv")

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
            data = {
                "real_base_cash": S["real_base_cash"],
                "paper": S["paper"],
                "paper_ais": S.get("paper_ais", {}),
                "shadow_fixed": S.get("shadow_fixed", {}),
                "real_watch": S.get("real_watch", {}),
            }
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
            paper_ais = data.get("paper_ais")
            if isinstance(paper_ais, dict):
                S["paper_ais"] = paper_ais
            shadow = data.get("shadow_fixed")
            if isinstance(shadow, dict):
                S["shadow_fixed"].update(shadow)
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

def telegram_notify_time_open():
    # 텔레그램 일반 알림은 평일 08:50~15:30까지만 보낸다.
    # 주문/자동매도 로직 자체는 막지 않고, 메시지만 시간 제한한다.
    if is_weekend_kst():
        return False
    sh, sm = parse_hhmm(TELEGRAM_NOTIFY_START, 8, 50)
    eh, em = parse_hhmm(TELEGRAM_NOTIFY_END, 15, 30)
    n = now_kst()
    return (sh, sm) <= (n.hour, n.minute) <= (eh, em)

def telegram_button(text, url):
    return {"text": text, "url": url}

def send_telegram(msg, buttons=None, force=False):
    # 텔레그램은 inline_keyboard 버튼이 카카오보다 안정적으로 보임.
    # 일반 매수/매도/상태 알림은 16:00 이후 차단한다.
    # 서버 오류처럼 꼭 필요한 알림은 force=True로 예외 전송할 수 있다.
    if (not force) and (not telegram_notify_time_open()):
        write_alert_log("SYSTEM", "telegram", "", 0, 0, "skipped", "TELEGRAM_NOTIFY_TIME_CLOSED", False, msg.split("\n")[0])
        return False, f"TELEGRAM 알림 시간 아님({TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END})"
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

def send_telegram_file(filepath, caption="", force=False):
    if (not force) and (not telegram_notify_time_open()):
        return False, f"TELEGRAM 알림 시간 아님({TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END}, 주말 제외)"
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
    """최종 최소알림 모드에서는 카카오 중복 전송을 끄고 텔레그램만 사용."""
    add_alert(msg)
    url = link_url or APP_URL or "https://developers.tossinvest.com/docs"
    if ENABLE_KAKAO_MIRROR:
        ok, text = post_kakao_template(kakao_template_text(msg, url, button_title))
    else:
        ok, text = False, "KAKAO_MIRROR_DISABLED"
    tg_ok, tg_text = send_telegram(msg, [[telegram_button(button_title, url)]])
    with LOCK:
        S["kakao_last"] = f"{now_text()} kakao={text} / telegram={tg_text}"
    return ok or tg_ok, f"kakao={text} / telegram={tg_text}"

def confirm_url(sym, side, qty=0):
    base = APP_URL or ""
    qs = urlencode({"symbol": sym, "side": side, "qty": str(qty)})
    return f"{base}/confirm?{qs}" if base else "/confirm?" + qs

def create_trade_button_url(sym, side, qty, alert_price, reason=""):
    """텔레그램 버튼용 1회성 주문 URL.
    - 버튼은 TELEGRAM_BUTTON_TTL_SEC 안에서만 유효
    - 클릭 시 현재가를 다시 확인하고 가격 괴리가 크면 차단
    - ENABLE_REAL_ORDER=false면 실제 주문은 place_order_manual에서 최종 차단됨
    """
    oid = uuid.uuid4().hex
    with LOCK:
        S.setdefault("pending_orders", {})[oid] = {
            "created_at": time.time(),
            "symbol": str(sym),
            "side": str(side),
            "qty": int(to_int(qty)),
            "alert_price": float(to_float(alert_price)),
            "reason": str(reason)[:200],
            "used": False,
        }
    qs = urlencode({"oid": oid})
    base = APP_URL or ""
    return f"{base}/telegram_order?{qs}" if base else "/telegram_order?" + qs

def handle_telegram_order(qs):
    """텔레그램 버튼 주문 처리.
    BUY는 하이닉스 2종목만 허용하고, 클릭 순간 METHOD/HYNIX 조건을 다시 검사한다.
    조건 불충족이면 주문하지 않고 '매수 실패'로 종료한다.
    """
    oid = (qs.get("oid") or [""])[0]
    with LOCK:
        item = S.setdefault("pending_orders", {}).get(oid)
    if not item:
        return {"ok": False, "message": "주문 버튼이 없거나 만료되었습니다."}
    if item.get("used"):
        return {"ok": False, "message": "이미 사용된 주문 버튼입니다."}

    age = time.time() - to_float(item.get("created_at", 0))
    if age > TELEGRAM_BUTTON_TTL_SEC:
        with LOCK:
            S["pending_orders"].pop(oid, None)
        return {"ok": False, "message": f"매수 실패: 주문 버튼 만료 {int(age)}초 경과. 새 신호를 기다리세요."}

    sym = str(item.get("symbol", ""))
    side = str(item.get("side", ""))
    qty = int(to_int(item.get("qty", 0)))
    alert_price = to_float(item.get("alert_price", 0))
    current_price = to_float(S.get("prices", {}).get(sym, 0))

    if side == "BUY":
        if not ENABLE_TELEGRAM_BUTTON_ORDER:
            return {"ok": False, "message": "매수 실패: 텔레그램 버튼매수가 비활성화되어 있습니다."}
        if ENABLE_REAL_AUTO_BUY:
            return {"ok": False, "message": "매수 실패: 자동매수 ON 상태에서는 버튼매수 혼동 방지를 위해 차단합니다."}
        if sym not in HYNIX_TRADE_SYMBOLS:
            return {"ok": False, "message": "매수 실패: 신규매수는 하이닉스 레버리지/인버스만 허용합니다."}
        ok_live, live_reason = method63_live_buy_ok(sym)
        if not ok_live:
            return {"ok": False, "message": f"매수 실패: {live_reason}"}
    else:
        if sym not in TRADE_ALLOWED_SYMBOLS:
            return {"ok": False, "message": "허용되지 않은 실전 매매 후보입니다."}

    if current_price <= 0 or alert_price <= 0:
        return {"ok": False, "message": "현재가 확인 실패. 주문 차단."}
    drift = pct(current_price, alert_price)
    # 매수는 알림가보다 비싸지면 차단, 매도는 알림가보다 크게 밀리면 차단
    if side == "BUY" and drift > MAX_BUTTON_PRICE_DRIFT_PCT:
        return {"ok": False, "message": f"매수 실패: 알림가 대비 +{drift:.2f}% 상승. 추격매수 금지."}
    if side == "SELL" and drift < -MAX_BUTTON_PRICE_DRIFT_PCT:
        return {"ok": False, "message": f"매도 재확인 필요: 알림가 대비 {drift:.2f}%"}

    with LOCK:
        S.setdefault("pending_orders", {}).setdefault(oid, {})["used"] = True
    result = place_order_manual(sym, side, qty)
    result["button_age_sec"] = round(age, 1)
    result["alert_price"] = alert_price
    result["current_price"] = current_price
    result["price_drift_pct"] = round(drift, 3)

    if result.get("ok") and side == "BUY" and sym in HYNIX_TRADE_SYMBOLS:
        method63_mark_buy_success(sym)
        result["auto_sell_watch"] = "ON"
        result["message"] = str(result.get("message", "성공")) + " / 자동매도 감시 ON"
    return result

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

def clear_token():
    # 토스가 401 invalid-token을 주면 서버 메모리에 남은 토큰을 버리고 재발급한다.
    with LOCK:
        S["token"] = ""
        S["token_exp"] = 0

def auth_headers(account=False):
    token = ensure_token() or ""
    h = {"Authorization": "Bearer " + token}
    with LOCK:
        acc = S["account_seq"]
    if account and acc:
        h["X-Tossinvest-Account"] = str(acc)  # 계좌는 절대 int 변환 금지
    return h

def _json_or_raw(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def _is_invalid_token(status_code, data):
    if status_code != 401:
        return False
    text = str(data).lower()
    return "invalid-token" in text or "invalid_token" in text or "유효하지 않은 토큰" in text or status_code == 401

def api_get(path, params=None, account=False, timeout=10):
    try:
        r = requests.get(BASE + path, headers=auth_headers(account), params=params or {}, timeout=timeout)
        data = _json_or_raw(r)

        # 401 invalid-token이면 조용히 토큰 캐시를 지우고 새 토큰으로 1회 재시도한다.
        # 재시도까지 실패했을 때만 빨간 오류로 남긴다.
        if _is_invalid_token(r.status_code, data):
            clear_token()
            r = requests.get(BASE + path, headers=auth_headers(account), params=params or {}, timeout=timeout)
            data = _json_or_raw(r)

            # 재시도 후에도 invalid-token이면 장외 계좌조회/토큰 갱신 흔들림으로 처리하고
            # 빨간 오류를 반복 저장하지 않는다. 가격 저장 루프는 계속 돈다.
            if _is_invalid_token(r.status_code, data):
                set_status_once(f"INVALID_TOKEN_{path}", f"토스 토큰 재발급 대기: {path}", INVALID_TOKEN_STATUS_COOLDOWN_SEC)
                return r.status_code, data

        # 429는 토스 요청 한도 초과다. 서버 장애가 아니므로 상태만 바꾸고 빨간 오류 폭탄은 막는다.
        if r.status_code == 429:
            set_status(f"토스 요청 제한 대기: {path}")
            return r.status_code, data

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
        data = _json_or_raw(r)

        # 주문/토큰 관련 POST도 401이면 새 토큰으로 1회 재시도한다.
        # 재시도까지 실패했을 때만 빨간 오류로 남긴다.
        if _is_invalid_token(r.status_code, data):
            clear_token()
            h = auth_headers(account)
            h["Content-Type"] = "application/json"
            r = requests.post(BASE + path, headers=h, json=body or {}, timeout=timeout)
            data = _json_or_raw(r)

            if _is_invalid_token(r.status_code, data):
                set_status_once(f"INVALID_TOKEN_POST_{path}", f"토스 토큰 재발급 대기: {path}", INVALID_TOKEN_STATUS_COOLDOWN_SEC)
                return r.status_code, data

        if r.status_code == 429:
            set_status(f"토스 요청 제한 대기: {path}")
            return r.status_code, data

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
        # 1주 테스트/관찰용 포지션은 실계좌 보유감시 알림에서 제외
        if qty <= 1:
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


def auto_sell_allowed_symbol(sym):
    if PAPER_ONLY_MODE or sym in REAL_ORDER_BLOCKED_SYMBOLS:
        return False
    if sym not in TRADE_ALLOWED_SYMBOLS:
        return False
    # 해외/이벤트/장기투자/관찰용은 제외. 이 리스트에 없는 종목은 자동매도하지 않는다.
    return sym in set(TRADE_ALLOWED_SYMBOLS)

def auto_sell_reason(sym, qty, price, buy, high, profit, drop_from_high):
    if not ENABLE_REAL_AUTO_SELL or not PEAK_PROFIT_TRAILING_AUTO_SELL:
        return None
    if not auto_sell_allowed_symbol(sym):
        return None
    if qty <= 1:
        return None
    if price <= 0 or buy <= 0 or high <= 0:
        return None
    # 삼성전자 레버리지 장기 보유분은 손실권 자동매도 절대 금지.
    # 환경변수가 잘못 바뀌어도 현재 수익률이 0% 이하이면 무조건 보유한다.
    if sym in REAL_PROFIT_ONLY_SYMBOLS and profit <= 0:
        return None
    # V4.13 본전방어:
    # 최고수익 +2% 이상 찍은 뒤 현재수익이 +0.3% 이하로 밀리면 방어매도
    max_profit = pct(high, buy)
    if BREAKEVEN_GUARD_AUTO_SELL and max_profit >= BREAKEVEN_GUARD_TRIGGER_PCT:
        if profit >= 0 and profit <= BREAKEVEN_GUARD_EXIT_PCT:
            return f"본전방어 자동매도: 최고수익={max_profit:.2f}%, 현재={profit:.2f}%, 고점대비={drop_from_high:.2f}%"

    # 손실권 자동손절은 기본 OFF. 수익권 자동매도만 한다.
    if AUTO_SELL_PROFIT_ONLY and profit < AUTO_SELL_MIN_PROFIT_PCT:
        return None
    if not AUTO_SELL_LOSS_CUT and profit < 0:
        return None
    # 장마감 수익권 정리
    if is_after_or_equal_hhmm(AUTO_SELL_FORCE_EXIT_TIME):
        if (not AUTO_SELL_FORCE_EXIT_ONLY_PROFIT) or profit > 0:
            return f"장마감 수익권 자동정리: 현재수익={profit:.2f}%"
    # 큰 수익 보호: 추세 확인보다 수익 보전을 우선
    max_profit = pct(high, buy)
    if max_profit >= AUTO_SELL_BIG_PROFIT_PCT and profit >= 0 and drop_from_high <= -AUTO_SELL_BIG_TRAIL_DROP_PCT:
        return f"큰 수익권 고점이탈 자동매도: 최고수익={max_profit:.2f}%, 현재={profit:.2f}%, 고점대비={drop_from_high:.2f}%"
    # 일반 수익 보호: 하이닉스 버튼매수 종목은 +2% 이후 -0.3%p 이탈이면 즉시 보호매도.
    if max_profit >= AUTO_SELL_PROFIT_START_PCT and profit >= AUTO_SELL_MIN_PROFIT_PCT and drop_from_high <= -AUTO_SELL_TRAIL_DROP_PCT:
        if sym in HYNIX_TRADE_SYMBOLS:
            return f"하이닉스 수익권 고점이탈 자동매도: 최고수익={max_profit:.2f}%, 현재={profit:.2f}%, 고점대비={drop_from_high:.2f}%"
        wm = S.get("wma", {}).get(sym, {})
        w5 = to_float(wm.get("wma5", 0))
        w20 = to_float(wm.get("wma20", 0))
        fam = symbol_family(sym)
        fam_mode = family_mode(fam) if FAMILY_MODE_ENGINE else target_market_regime()
        opps = opposite_symbols_for(sym)
        opp_strong = any(low_rise_pct(o) >= 1.0 and price_change_pct(o) >= 0.2 for o in opps)
        trend_weak = (w5 and w20 and w5 < w20) or opp_strong or (fam_mode == "DOWN" and not is_inverse_symbol(sym)) or (fam_mode in ["UP", "RECOVERY"] and is_inverse_symbol(sym))
        if trend_weak:
            return f"수익권 고점이탈 자동매도: 최고수익={max_profit:.2f}%, 현재={profit:.2f}%, 고점대비={drop_from_high:.2f}%, 계열={fam}:{fam_mode}"
    return None

def execute_real_auto_sell(sym, qty, reason):
    if not ENABLE_REAL_ORDER:
        write_alert_log("AUTOSELL", "blocked", sym, S["prices"].get(sym, 0), 0, "blocked", "ENABLE_REAL_ORDER=false", False, reason)
        return False
    sellable = int(get_sellable_quantity(sym, force=True))
    qty = min(int(to_int(qty)), sellable)
    if qty <= 0:
        write_alert_log("AUTOSELL", "blocked", sym, S["prices"].get(sym, 0), 0, "blocked", "매도가능수량 없음", False, reason)
        return False
    result = place_order_manual(sym, "SELL", qty)
    ok = bool(result.get("ok"))

    if ok and sym in [LEV, INV]:
        # 세트 카운트는 매수 성공 시 이미 증가한다.
        # 매도 완료 시에는 반대방향 10분 대기 기준 시간만 기록한다.
        method63_mark_exit(sym)
    price = S["prices"].get(sym, 0)
    title = "🔴 수익보호 자동매도 완료" if ok else "⚠️ 수익보호 자동매도 실패"
    msg = (
        f"{title}\n"
        f"종목: {name_of(sym)} ({sym})\n"
        f"수량: {qty}주\n"
        f"현재가: {fmt_won(price)}\n"
        f"사유: {reason}\n"
        f"결과: {result.get('message', '')}"
    )
    if ENABLE_REAL_AUTOSELL_RESULT_ALERT:
        send_telegram(msg, [[telegram_button("📊 대시보드", APP_URL)]])
    write_alert_log("AUTOSELL", "real_auto_sell", sym, price, 0, "SELL" if ok else "FAILED", reason, ok, json.dumps(result, ensure_ascii=False)[:300])
    return ok

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
        qty = to_float(item.get("qty", 0))
        # 1주 테스트/관찰용 포지션은 보유관리 알림 제외
        if qty <= 1:
            continue
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

        # V4.12: 매수는 사용자가 선택하더라도, 수익권 매도는 시스템이 자동으로 보호한다.
        reason_auto = auto_sell_reason(sym, qty, price, buy, high, profit, drop_from_high)
        if reason_auto:
            if execute_real_auto_sell(sym, qty, reason_auto):
                continue

        # 자동매도 실행은 유지하되, 보유 약화/손실/교체 후보 같은 반복 경고는 끈다.
        if FINAL_MINIMAL_ALERT_MODE or not ENABLE_HOLDING_WARNING_ALERT:
            continue

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

def parse_sellable_qty(data):
    r = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(r, dict):
        for k in ["sellableQuantity", "sellableQty", "quantity", "qty"]:
            if k in r:
                return to_float(r[k])
    return 0

def get_sellable_quantity(sym, force=False):
    """
    sellable-quantity는 토스 요청 한도에 쉽게 걸린다.
    그래서 평소에는 캐시를 쓰고, 실제 매도 실행 직전에만 force=True로 1종목 조회한다.
    """
    sym = str(sym or "")
    if not sym:
        return 0
    now_ts = time.time()
    with LOCK:
        cache = S.get("sellable_cache", {}).get(sym, {})
        holding_qty = to_float(S.get("hold_qty", {}).get(sym, 0))
    if not force and isinstance(cache, dict):
        cached_at = to_float(cache.get("ts", 0))
        if cached_at and now_ts - cached_at < SELLABLE_CACHE_SEC:
            return to_float(cache.get("qty", 0))

    code, data = api_get("/api/v1/sellable-quantity", params={"symbol": sym}, account=True, timeout=8)
    if code == 200:
        qty = parse_sellable_qty(data)
    else:
        # 429/일시 오류면 기존 캐시를 먼저 쓰고, 없으면 보유수량으로 fallback.
        qty = to_float(cache.get("qty", 0)) if isinstance(cache, dict) else 0
        if qty <= 0:
            qty = holding_qty

    with LOCK:
        S.setdefault("sellable_cache", {})[sym] = {"qty": qty, "ts": now_ts}
        S.setdefault("sellable", {})[sym] = qty
    return qty

def load_sellable_quantities():
    """
    기존처럼 26개 전 종목 sellable-quantity를 30초마다 조회하면 429가 난다.
    이제는 실제 보유 중이고 2주 이상인 종목만 조회한다.
    1주 테스트 포지션은 조회/알림 대상에서 제외한다.
    """
    with LOCK:
        holding_qty = dict(S.get("hold_qty", {}))
        old_sellable = dict(S.get("sellable", {}))

    sellable = dict(old_sellable)
    targets = [sym for sym, qty in holding_qty.items() if sym and to_float(qty) >= SELLABLE_MIN_QTY]

    for sym in targets:
        sellable[sym] = get_sellable_quantity(sym, force=False)

    # 보유가 사라진 종목은 sellable 표시도 정리한다.
    active = set(targets)
    for sym in list(sellable.keys()):
        if sym not in active:
            sellable.pop(sym, None)

    with LOCK:
        S["sellable"] = sellable
    return True

def refresh_account_all(force=False):
    # 장 마감 후에는 계좌 API를 30초마다 때리지 않는다.
    # 데이터 저장/가격 저장은 load_prices + write_logs가 계속 담당한다.
    if not force and not account_api_time_open():
        set_status_once("ACCOUNT_REFRESH_CLOSED", "장외: 계좌조회 중지, 가격/CSV 저장만 유지", 300)
        return True

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
    return True

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
            api_ts = str(item.get("timestamp", ""))
            api_dt = parse_api_datetime(api_ts)
            # 장중에는 오늘 날짜가 아닌 시세를 절대 현재가로 채택하지 않는다.
            if ENABLE_MARKET_SAFETY_GATE and api_dt and api_dt.strftime("%Y-%m-%d") != today():
                continue
            S.setdefault("market_data_capture", {}).setdefault("price_timestamp", {})[sym] = api_ts
            old = S["prices"].get(sym, price)
            S["prev_prices"][sym] = old
            S["prices"][sym] = price
            hist = S["history"].setdefault(sym, [])
            hist.append(price)
            if len(hist) > TARGET_PATTERN_LOOKBACK_POINTS:
                del hist[:-TARGET_PATTERN_LOOKBACK_POINTS]
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
# OPERATING V4 시장상태 / 실행제한 헬퍼
# ============================================================

def hhmm_tuple(hhmm):
    h, m = parse_hhmm(hhmm)
    return h, m

def is_before_hhmm(hhmm):
    h, m = hhmm_tuple(hhmm)
    n = now_kst()
    return (n.hour, n.minute) < (h, m)

def is_after_or_equal_hhmm(hhmm):
    h, m = hhmm_tuple(hhmm)
    n = now_kst()
    return (n.hour, n.minute) >= (h, m)

def buy_time_blocked():
    return is_before_hhmm(NO_BUY_BEFORE) or is_after_or_equal_hhmm(NO_NEW_BUY_AFTER)

def paper_auto_time_open():
    # AI 가상 자동운영은 지정 시간 안에서만 돈을 움직인다.
    # 15:20 정산 신호를 처리하기 위해 종료 분까지는 허용하고, 15:21부터 완전 정지한다.
    sh, sm = hhmm_tuple(PAPER_AUTO_START)
    eh, em = hhmm_tuple(PAPER_AUTO_END)
    n = now_kst()
    cur = (n.hour, n.minute)
    return cur >= (sh, sm) and cur <= (eh, em)

def record_paper_wait_once(reason, mode):
    # CHOPPY/NO_TRADE 관망 로그가 30초마다 쌓이는 것을 막는다.
    key = f"PAPER_WAIT_{mode}_{reason}"
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < PAPER_WAIT_LOG_COOLDOWN_SEC:
            return False
        S["last_alert"][key] = time.time()
    record_paper("AI자동관망", "", 0, 0, reason, strategy="WAIT", mode=mode, source="AUTO")
    return True

def is_inverse_symbol(sym):
    return sym in INVERSE_SYMBOLS or "인버스" in name_of(sym)

def is_long_allowed_symbol(sym, mode):
    if mode == "SEMI_LEADER_UP":
        return sym in SEMI_LONG_SYMBOLS
    if mode == "UP":
        return sym in UP_LONG_SYMBOLS
    return False

def symbol_strength(sym):
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return 0
    score = to_float(S["signals"].get(sym, {}).get("score", raw_symbol_score(sym)))
    chg = price_change_pct(sym)
    lrise = low_rise_pct(sym)
    hdrop = high_drop_pct(sym)
    vr = volume_ratio(sym)
    strength = score
    strength += max(chg, 0) * 8
    strength += max(lrise, 0) * 2
    strength -= max(-hdrop, 0) * 1.5 if hdrop < -4 else 0
    strength += min(vr, 3) * 2
    return strength

def semiconductor_strong():
    core = [LEV, HYNIX, "494310", "488080", "469150"]
    strong = 0
    for sym in core:
        score = to_float(S["signals"].get(sym, {}).get("score", raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        lrise = low_rise_pct(sym)
        if score >= 65 or chg >= 0.3 or lrise >= 1.0:
            strong += 1
    inverse_weak = True
    for sym in [INV, "252670", "0193L0"]:
        score = to_float(S["signals"].get(sym, {}).get("score", raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        if score >= 62 and chg > 0:
            inverse_weak = False
    return strong >= 2 and inverse_weak

def inverse_market_confirmed():
    weak_long = 0
    for sym in [LEV, HYNIX, "494310", "488080", "122630", "069500", "233740"]:
        score = to_float(S["signals"].get(sym, {}).get("score", raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        hdrop = high_drop_pct(sym)
        if score <= 45 or chg <= -0.3 or hdrop <= -1.5:
            weak_long += 1
    strong_inv = 0
    for sym in INVERSE_SYMBOLS:
        score = to_float(S["signals"].get(sym, {}).get("score", raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        lrise = low_rise_pct(sym)
        if score >= 58 and (chg > 0 or lrise >= 0.7):
            strong_inv += 1
    return weak_long >= 4 and strong_inv >= 1

def operating_market_mode():
    market_total = to_float(S["market_score"].get("total", 50))
    label = S["market_score"].get("label", "")
    if semiconductor_strong() and market_total >= 42:
        return "SEMI_LEADER_UP"
    if inverse_market_confirmed() and (market_total <= 42 or label == "하락장"):
        return "DOWN"

    ups = downs = movers = 0
    for sym in ALERT_SYMBOLS:
        chg = price_change_pct(sym)
        hdrop = high_drop_pct(sym)
        lrise = low_rise_pct(sym)
        if chg >= 0.25 or lrise >= 1.0:
            ups += 1
        if chg <= -0.25 or hdrop <= -1.0:
            downs += 1
        if abs(chg) >= 0.25 or abs(hdrop) >= 1.0 or abs(lrise) >= 1.0:
            movers += 1

    if market_total >= 65 or label == "상승장":
        return "UP"
    if movers >= 3 and ups >= 1 and downs >= 1:
        return "CHOPPY"
    return "NO_TRADE"

def choose_best_symbol(candidates):
    valid = []
    for sym in candidates:
        price = S["prices"].get(sym, 0)
        if price <= 0:
            continue
        if bad_news_risk_detected(sym):
            continue
        valid.append((symbol_strength(sym), sym))
    if not valid:
        return None
    valid.sort(reverse=True)
    return valid[0][1]

def log_execution_block(reason, sym=""):
    write_alert_log("BLOCK", "execution", sym, S["prices"].get(sym, 0), 0, "blocked", reason, False, "")

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
    """
    V4.13:
    - 실계좌 행동 알림은 METHOD63 하이닉스 전용 신호를 최우선으로 보냄
    - 09:05 기존 오신호는 NO_BUY_BEFORE=09:15로 차단
    - 기존 보조 알림은 ALERT_ONLY_ACTIONABLE=true이면 계속 차단
    """
    if FINAL_MINIMAL_ALERT_MODE or not ENABLE_GENERAL_SIGNAL_ALERT:
        return
    if not is_market_watch_time():
        return

    # V4.13 최우선: 하이닉스 레버리지/인버스 METHOD63 후보
    send_method63_alert()

    # 기존 보조 알림은 사용자 혼란 방지를 위해 기본 차단
    if ALERT_ONLY_ACTIONABLE:
        return

    mode = operating_market_mode()
    if mode in ["CHOPPY", "NO_TRADE"]:
        return

    for sym in ALERT_SYMBOLS:
        if bad_news_risk_detected(sym):
            send_alert_once(f"RISK_{sym}", sym, "⚠️ 악재성 급락 의심")


# ============================================================
# V4.10 목표 패턴 공통 판단 함수
# - 리플레이/실시간/AI가상/실계좌 알림이 이 함수를 같이 사용해야 함
# ============================================================

def target_pattern_reset_if_new_day():
    with LOCK:
        tp = S.setdefault("target_pattern", {})
        if tp.get("date") != today():
            S["target_pattern"] = {
                "date": today(),
                "sent_count": 0,
                "stages": {},
                "last_choice": {},
                "last_action": "새 장 시작",
            }


def recent_change_pct(sym, n=5):
    hist = S.get("history", {}).get(sym, [])
    if not hist or len(hist) <= n:
        return 0.0
    return pct(hist[-1], hist[-1-n])


# ============================================================
# V4.13 METHOD 63 하이닉스 전용 매수 후보 엔진
# ============================================================

def method63_reset_if_new_day():
    with LOCK:
        m = S.setdefault("method63", {})
        if m.get("date") != today():
            S["method63"] = {
                "date": today(),
                "set_count": 0,
                "last_side": "",
                "last_exit_ts": 0,
                "last_alert_ts": {},
                "last_action": "새 장 시작",
            }


def method63_time_open():
    if is_before_hhmm(METHOD63_START_TIME):
        return False
    if is_after_or_equal_hhmm(METHOD63_NO_NEW_BUY_AFTER):
        return False
    return True


def method63_side_blocked(side):
    method63_reset_if_new_day()

    with LOCK:
        m = S.setdefault("method63", {})
        set_count = int(to_int(m.get("set_count", 0)))
        last_side = str(m.get("last_side", ""))
        last_exit_ts = to_float(m.get("last_exit_ts", 0))

    # 이미 하이닉스 레버리지/인버스 보유 중이면 새 매수 신호는 막는다.
    with LOCK:
        hold_qty_map = dict(S.get("hold_qty", {}))
        real_watch_map = dict(S.get("real_watch", {}))
    if to_float(hold_qty_map.get(LEV, 0)) > 1 or to_float(hold_qty_map.get(INV, 0)) > 1 or LEV in real_watch_map or INV in real_watch_map:
        return True, "하이닉스 포지션 보유 중: 신규매수 금지"

    if set_count >= METHOD63_MAX_SETS_PER_DAY:
        return True, "하루 최대 2세트 완료"

    if (not METHOD63_SAME_DIRECTION_REENTRY) and last_side == side:
        return True, "같은 방향 재진입 금지"

    if last_side and last_side != side and last_exit_ts > 0:
        passed = time.time() - last_exit_ts
        if passed < METHOD63_REVERSE_WAIT_SEC:
            remain = int(METHOD63_REVERSE_WAIT_SEC - passed)
            return True, f"반대 방향 전환 대기 {remain}초"

    return False, ""


def method63_candidate():
    """
    METHOD63:
    미래 데이터 없이 현재까지 쌓인 가격, high, low, history만 사용.
    실계좌 자동매수는 하지 않고 매수 후보 알림만 만든다.
    """
    if not METHOD63_HYNIX_ENGINE:
        return None

    if not method63_time_open():
        return None

    lev_price = to_float(S.get("prices", {}).get(LEV, 0))
    inv_price = to_float(S.get("prices", {}).get(INV, 0))

    if lev_price <= 0 or inv_price <= 0:
        return None

    lev_lrise = low_rise_pct(LEV)
    inv_lrise = low_rise_pct(INV)

    lev_hdrop = high_drop_pct(LEV)
    inv_hdrop = high_drop_pct(INV)

    lev_recent = recent_change_pct(LEV, METHOD63_RECENT_POINTS)
    inv_recent = recent_change_pct(INV, METHOD63_RECENT_POINTS)

    inv_ok = (
        inv_lrise >= METHOD63_INV_LOW_RISE_PCT
        and lev_hdrop <= -METHOD63_OPPOSITE_WEAK_PCT
        and inv_recent >= METHOD63_RECENT_UP_PCT
    )

    lev_ok = (
        lev_lrise >= METHOD63_LEV_LOW_RISE_PCT
        and inv_hdrop <= -METHOD63_OPPOSITE_WEAK_PCT
        and lev_recent >= METHOD63_RECENT_UP_PCT
    )

    candidates = []

    if inv_ok:
        blocked, block_reason = method63_side_blocked("INV")
        if not blocked:
            candidates.append({
                "side": "INV",
                "symbol": INV,
                "name": name_of(INV),
                "price": inv_price,
                "score": inv_lrise + abs(lev_hdrop) + inv_recent,
                "reason": (
                    f"인버스 저점대비 +{inv_lrise:.2f}% / "
                    f"레버리지 고점대비 {lev_hdrop:.2f}% / "
                    f"최근{METHOD63_RECENT_POINTS}분 +{inv_recent:.2f}%"
                ),
            })

    if lev_ok:
        blocked, block_reason = method63_side_blocked("LEV")
        if not blocked:
            candidates.append({
                "side": "LEV",
                "symbol": LEV,
                "name": name_of(LEV),
                "price": lev_price,
                "score": lev_lrise + abs(inv_hdrop) + lev_recent,
                "reason": (
                    f"레버리지 저점대비 +{lev_lrise:.2f}% / "
                    f"인버스 고점대비 {inv_hdrop:.2f}% / "
                    f"최근{METHOD63_RECENT_POINTS}분 +{lev_recent:.2f}%"
                ),
            })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[0]



def method63_live_buy_ok(sym):
    """텔레그램 버튼 클릭 순간 다시 확인하는 하이닉스 매수 조건."""
    if sym not in HYNIX_TRADE_SYMBOLS:
        return False, "하이닉스 레버리지/인버스가 아닙니다."
    if not method63_time_open():
        return False, f"매수 가능 시간이 아닙니다({METHOD63_START_TIME}~{METHOD63_NO_NEW_BUY_AFTER})."

    lev_price = to_float(S.get("prices", {}).get(LEV, 0))
    inv_price = to_float(S.get("prices", {}).get(INV, 0))
    if lev_price <= 0 or inv_price <= 0:
        return False, "하이닉스 레버리지/인버스 현재가 확인 실패"

    lev_lrise = low_rise_pct(LEV)
    inv_lrise = low_rise_pct(INV)
    lev_hdrop = high_drop_pct(LEV)
    inv_hdrop = high_drop_pct(INV)
    lev_recent = recent_change_pct(LEV, METHOD63_RECENT_POINTS)
    inv_recent = recent_change_pct(INV, METHOD63_RECENT_POINTS)

    if sym == INV:
        blocked, block_reason = method63_side_blocked("INV")
        if blocked:
            return False, block_reason
        ok = inv_lrise >= METHOD63_INV_LOW_RISE_PCT and lev_hdrop <= -METHOD63_OPPOSITE_WEAK_PCT and inv_recent >= METHOD63_RECENT_UP_PCT
        reason = f"인버스 조건 재검사: 저점대비 +{inv_lrise:.2f}%, 레버리지 고점대비 {lev_hdrop:.2f}%, 최근{METHOD63_RECENT_POINTS}개 {inv_recent:.2f}%"
        return (True, reason) if ok else (False, reason)

    if sym == LEV:
        blocked, block_reason = method63_side_blocked("LEV")
        if blocked:
            return False, block_reason
        ok = lev_lrise >= METHOD63_LEV_LOW_RISE_PCT and inv_hdrop <= -METHOD63_OPPOSITE_WEAK_PCT and lev_recent >= METHOD63_RECENT_UP_PCT
        reason = f"레버리지 조건 재검사: 저점대비 +{lev_lrise:.2f}%, 인버스 고점대비 {inv_hdrop:.2f}%, 최근{METHOD63_RECENT_POINTS}개 {lev_recent:.2f}%"
        return (True, reason) if ok else (False, reason)

    return False, "알 수 없는 종목"


def method63_mark_buy_success(sym):
    """텔레그램 버튼매수 성공 시 1세트를 사용한 것으로 기록한다."""
    method63_reset_if_new_day()
    side = "INV" if sym == INV else "LEV" if sym == LEV else ""
    if not side:
        return
    with LOCK:
        m = S.setdefault("method63", {})
        m["set_count"] = int(to_int(m.get("set_count", 0))) + 1
        m["last_side"] = side
        m["last_action"] = f"{now_short()} METHOD/HYNIX 버튼매수 성공 {name_of(sym)}"
    save_state()


def method63_mark_exit(sym):
    """하이닉스 자동매도 완료 시 반대방향 10분 대기 기준 시간을 기록한다."""
    method63_reset_if_new_day()
    side = "INV" if sym == INV else "LEV" if sym == LEV else ""
    if not side:
        return
    with LOCK:
        m = S.setdefault("method63", {})
        m["last_side"] = side
        m["last_exit_ts"] = time.time()
        m["last_action"] = f"{now_short()} METHOD/HYNIX 자동매도 완료 {name_of(sym)}"
    save_state()


def method63_alert_cooldown_ok(side):
    method63_reset_if_new_day()

    with LOCK:
        m = S.setdefault("method63", {})
        last_map = m.setdefault("last_alert_ts", {})
        last = to_float(last_map.get(side, 0))

    return time.time() - last >= METHOD63_ALERT_COOLDOWN_SEC


def mark_method63_alert_sent(side):
    method63_reset_if_new_day()

    with LOCK:
        m = S.setdefault("method63", {})
        m.setdefault("last_alert_ts", {})[side] = time.time()
        m["last_action"] = f"{now_short()} METHOD63 {side} 알림"


def send_method63_alert():
    """METHOD63 전용 매수 후보 알림. 최종 최소알림 모드에서는 기본 차단."""
    if FINAL_MINIMAL_ALERT_MODE or not ENABLE_METHOD63_CANDIDATE_ALERT:
        return False
    cand = method63_candidate()

    if not cand:
        return False

    side = cand["side"]
    sym = cand["symbol"]
    price = cand["price"]

    if not method63_alert_cooldown_ok(side):
        return False

    try:
        step_cash = SWING_BUY_STEP_AMOUNTS[0] if SWING_BUY_STEP_AMOUNTS else 0
        qty = int((step_cash * ORDER_SAFE_RATIO) // price) if price > 0 else 0
    except Exception:
        qty = 0

    buy_url = create_trade_button_url(sym, "BUY", qty, price, "METHOD/HYNIX 버튼매수 후보")
    confirm = confirm_url(sym, "BUY", qty)
    dashboard_url = APP_URL or "https://market-watch-6zgo.onrender.com"

    title = "하이닉스 인버스 우세" if side == "INV" else "하이닉스 레버리지 회복"

    msg = (
        f"🟢 METHOD63 하이닉스 매수 후보\n"
        f"종목: {cand['name']} ({sym})\n"
        f"현재가: {fmt_won(price)}\n"
        f"추천수량: {qty}주\n"
        f"판정: {title}\n"
        f"근거: {cand['reason']}\n"
        f"규칙: 09:15 이후 / 하루 최대 2세트 / 같은 방향 재진입 금지\n"
        f"주의: 자동매수 아님. 텔레그램 버튼은 {TELEGRAM_BUTTON_TTL_SEC}초 안에만 유효. 클릭 시 조건 재검사."
    )

    ok, resp = send_telegram(
        msg,
        [
            [telegram_button(f"🟢 {TELEGRAM_BUTTON_TTL_SEC}초 매수 실행", buy_url)],
            [telegram_button("확인화면", confirm), telegram_button("📊 대시보드", dashboard_url)],
        ],
    )

    write_alert_log(
        "METHOD63",
        "method63_buy_candidate",
        sym,
        price,
        0,
        "BUY_CANDIDATE",
        cand["reason"],
        ok,
        resp,
    )

    add_alert(msg)
    mark_method63_alert_sent(side)

    return ok


def family_groups():
    return {
        "HYNIX": {"long": [LEV, "494310", HYNIX], "inv": [INV]},
        "SAMSUNG": {"long": ["0193W0", "005930"], "inv": ["0193L0"]},
        "KOSPI": {"long": ["122630", "069500"], "inv": ["252670"]},
        "KOSDAQ": {"long": ["233740", "229200"], "inv": ["251340"]},
    }

def family_mode(name):
    g = family_groups().get(name, {})
    long_syms = g.get("long", [])
    inv_syms = g.get("inv", [])
    def avg(fn, syms):
        vals = [fn(s) for s in syms if S["prices"].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0.0
    long_chg = avg(price_change_pct, long_syms)
    inv_chg = avg(price_change_pct, inv_syms)
    long_low_rise = avg(low_rise_pct, long_syms)
    inv_low_rise = avg(low_rise_pct, inv_syms)
    long_high_drop = avg(high_drop_pct, long_syms)
    inv_high_drop = avg(high_drop_pct, inv_syms)
    if inv_chg >= 0.25 and inv_low_rise >= 0.7 and long_chg <= 0.1:
        return "DOWN"
    if long_chg >= 0.25 and long_low_rise >= 0.7 and inv_chg <= 0.3:
        return "UP"
    if long_high_drop <= -3.0 and long_low_rise >= RECOVERY_LOW_RISE_PCT and inv_chg <= 0.5:
        return "RECOVERY"
    if abs(long_chg) >= 0.25 or abs(inv_chg) >= 0.25 or long_low_rise >= 1.0 or inv_low_rise >= 1.0:
        return "CHOPPY"
    return "NO_TRADE"

def symbol_family(sym):
    for fname, g in family_groups().items():
        if sym in g.get("long", []) or sym in g.get("inv", []):
            return fname
    return "OTHER"

def opposite_symbols_for(sym):
    fam = symbol_family(sym)
    g = family_groups().get(fam, {})
    return g.get("long", []) if is_inverse_symbol(sym) else g.get("inv", [])

def opposite_weak(sym):
    opps = opposite_symbols_for(sym)
    if not opps:
        return True
    weak = 0
    for o in opps:
        if price_change_pct(o) <= 0.2 or high_drop_pct(o) <= -0.8:
            weak += 1
    return weak >= max(1, len(opps)//2)

def recovery_candidate_ready(sym):
    """V4.12 핵심: 현재 빨간색보다 당일/VI 이후 저점에서 살아나는지 확인."""
    if not RECOVERY_CANDIDATE_ENGINE:
        return False, "회복엔진 OFF"
    if sym not in TRADE_ALLOWED_SYMBOLS or is_inverse_symbol(sym):
        return False, "회복 후보 대상 아님"
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return False, "현재가 없음"
    rise = low_rise_pct(sym)
    r5 = recent_change_pct(sym, 5)
    r10 = recent_change_pct(sym, 10)
    wm = S.get("wma", {}).get(sym, {})
    w5 = to_float(wm.get("wma5", 0))
    w20 = to_float(wm.get("wma20", 0))
    family = symbol_family(sym)
    fam_mode = family_mode(family) if FAMILY_MODE_ENGINE else target_market_regime()
    if rise < RECOVERY_LOW_RISE_PCT:
        return False, f"저점대비 회복 부족 {rise:.2f}%"
    if r5 < RECOVERY_RECENT_UP_PCT and r10 < RECOVERY_RECENT_UP_PCT:
        return False, f"최근 상승 부족 5분={r5:.2f}% 10분={r10:.2f}%"
    if w5 and w20 and w5 < w20 and rise < RECOVERY_STRONG_LOW_RISE_PCT:
        return False, "WMA 회복 부족"
    if not opposite_weak(sym):
        return False, "반대 방향 약화 부족"
    if fam_mode not in ["UP", "RECOVERY", "CHOPPY"]:
        return False, f"계열모드 부적합 {family}:{fam_mode}"
    return True, f"회복반등: {family} {fam_mode}, 저점대비={rise:.2f}%, 5분={r5:.2f}%, 10분={r10:.2f}%"

def target_market_regime():
    """시장상황 분류: RECOVERY/UP/DOWN/CHOPPY/NO_TRADE.
    점수형 매수는 쓰지 않고, 롱/인버스 그룹의 실제 흐름으로 먼저 분류한다.
    """
    long_syms = [LEV, "494310", "0193W0", "122630", "233740"]
    inv_syms = ["252670", "251340", INV, "0193L0"]

    def avg_change(syms):
        vals = [price_change_pct(s) for s in syms if S["prices"].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    def avg_low_rise(syms):
        vals = [low_rise_pct(s) for s in syms if S["prices"].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    def avg_high_drop(syms):
        vals = [high_drop_pct(s) for s in syms if S["prices"].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    long_chg = avg_change(long_syms)
    inv_chg = avg_change(inv_syms)
    long_drop = avg_high_drop(long_syms)
    inv_drop = avg_high_drop(inv_syms)
    long_rise = avg_low_rise(long_syms)

    if inv_chg >= 0.4 and long_chg <= -0.25 and long_drop <= -1.0:
        return "DOWN"
    if long_chg >= 0.35 and inv_chg <= 0.2:
        return "UP"
    # 큰 하락 후 저점 대비 회복: 24일 같은 회복장
    if long_drop <= -TARGET_LONG_PULLBACK_PCT and long_rise >= 2.0 and inv_chg < 1.0:
        return "RECOVERY"
    movers = sum(1 for s in long_syms + inv_syms if abs(price_change_pct(s)) >= 0.3)
    mixed = (long_chg > 0 and inv_chg > 0) or (long_chg < 0 and inv_chg < 0)
    if movers >= 3 and mixed:
        return "CHOPPY"
    return "NO_TRADE"

def target_symbol_priority(mode):
    if mode == "DOWN":
        return REAL_INVERSE_PRIORITY
    if mode in ["UP", "RECOVERY"]:
        # 하이닉스 레버리지/반도체/삼성/KOSPI/KOSDAQ 순서.
        # 현재 빨간색 1등이 아니라 회복 후보도 target_choose_symbol에서 별도 평가한다.
        return REAL_LONG_PRIORITY
    return []

def target_rebreak_ready(sym, mode):
    """첫 반등 금지 + 반등 고점 재돌파 확인.
    현재까지 들어온 history만 사용하므로 미래 데이터 사용이 없다.
    """
    hist = S["history"].get(sym, [])
    if len(hist) < 10:
        return False, "history 부족"

    cur = hist[-1]
    first = hist[0]
    hi = max(hist)
    lo = min(hist)
    hi_idx = hist.index(hi)
    lo_idx = hist.index(lo)
    pullback = pct(lo, hi)
    rise_from_low = pct(cur, lo)
    chg_from_first = pct(cur, first)

    # 하락장 인버스: 26일 같은 날은 인버스 조기 진입 허용
    if mode == "DOWN":
        if not is_inverse_symbol(sym):
            return False, "DOWN인데 인버스 아님"
        inv_group_ok = inverse_market_confirmed() or price_change_pct(sym) >= 0.4 or low_rise_pct(sym) >= 1.0
        long_weak = sum(1 for s in [LEV, "0193W0", "122630", "233740", "494310"] if high_drop_pct(s) <= -1.0 or price_change_pct(s) <= -0.3)
        if inv_group_ok and long_weak >= 3 and rise_from_low >= 0.7:
            return True, f"하락장 인버스 조기확인: 롱약세={long_weak}, 저점대비={rise_from_low:.2f}%"
        return False, "인버스 확인 부족"

    if mode not in ["UP", "RECOVERY"]:
        return False, f"{mode} 매수대상 아님"
    if is_inverse_symbol(sym):
        return False, "롱 모드에서 인버스 제외"

    # 큰 눌림 요건. 회복장은 더 강하게 확인.
    need_pullback = -TARGET_LONG_MAJOR_PULLBACK_PCT if mode == "RECOVERY" else -TARGET_LONG_PULLBACK_PCT
    if pullback > need_pullback:
        return False, f"큰 눌림 부족 {pullback:.2f}%"

    # 저점이 고점 이후에 나와야 정상적인 눌림.
    if lo_idx <= hi_idx:
        return False, "저점이 고점 이후 구조가 아님"

    after_low = hist[lo_idx:]
    if len(after_low) < 5:
        return False, "저점 후 확인 부족"
    # 첫 반등 고점과 그 이후 눌림을 확인.
    rebound_window = after_low[:max(3, min(20, len(after_low)))]
    first_rebound_high = max(rebound_window)
    # 첫 반등 고점 돌파 버퍼
    rebreak_level = first_rebound_high * (1 + TARGET_REBREAK_BUFFER_PCT / 100)
    if cur < rebreak_level:
        return False, f"재돌파 전: 현재 {cur:.0f} < {rebreak_level:.0f}"
    if rise_from_low < 2.0:
        return False, f"저점대비 회복 부족 {rise_from_low:.2f}%"

    # 반대 인버스가 여전히 강하면 롱 금지.
    inv_too_strong = any(price_change_pct(s) > 0.5 and low_rise_pct(s) > 1.0 for s in REAL_INVERSE_PRIORITY)
    if inv_too_strong and mode != "UP":
        return False, "인버스 동시강세"

    return True, f"{mode} 재돌파 확인: 눌림={pullback:.2f}%, 저점대비={rise_from_low:.2f}%"

def target_choose_symbol(mode):
    # 1) V4.12 회복 반등 우선: 오늘 저점/VI 이후 저점에서 살아나는 종목
    #    예: 인버스 매도 후 하이닉스 레버리지 회복.
    if RECOVERY_CANDIDATE_ENGINE and mode in ["UP", "RECOVERY", "CHOPPY", "NO_TRADE"]:
        recovery_candidates = [LEV, "494310", "0193W0", "122630", "233740", "069500", "229200"]
        valid = []
        for sym in recovery_candidates:
            if S["prices"].get(sym, 0) <= 0:
                continue
            ok, reason = recovery_candidate_ready(sym)
            if ok:
                valid.append((low_rise_pct(sym) + recent_change_pct(sym, 10) * 2 + symbol_strength(sym) / 50, sym, reason))
        if valid:
            valid.sort(reverse=True)
            _, sym, reason = valid[0]
            return sym, reason

    # 2) 기존 장중 스윙 패턴
    for sym in target_symbol_priority(mode):
        if S["prices"].get(sym, 0) <= 0:
            continue
        ok, reason = target_rebreak_ready(sym, mode)
        if ok:
            return sym, reason
    return None, "조건 충족 종목 없음"

def target_next_stage_amount(sym):
    with LOCK:
        stages = S.setdefault("target_pattern", {}).setdefault("stages", {})
        stage = int(stages.get(sym, 0))
    if stage >= len(SWING_BUY_STEP_AMOUNTS):
        return 0, stage
    return SWING_BUY_STEP_AMOUNTS[stage], stage + 1

def send_real_pattern_buy_alert(sym, amount, stage, reason):
    # 신규매수 텔레그램 알림은 하이닉스 레버리지/인버스만 허용한다.
    # 삼성/코스피/코스닥/반도체/AI 점수 후보는 화면/CSV 참고용으로만 둔다.
    if sym not in HYNIX_TRADE_SYMBOLS:
        write_alert_log("REAL", "target_buy_blocked", sym, S["prices"].get(sym, 0), 0, "BLOCKED", "신규매수 알림은 하이닉스 2종목만 허용", False, "hynix_only")
        return False
    price = S["prices"].get(sym, 0)
    qty = int((amount * ORDER_SAFE_RATIO) // price) if price > 0 else 0
    if qty <= 0:
        return False
    key = f"TARGET_BUY_{today()}_{sym}_{stage}"
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < TARGET_REAL_ALERT_COOLDOWN_SEC:
            return False
        S["last_alert"][key] = time.time()
        S.setdefault("target_pattern", {}).setdefault("stages", {})[sym] = stage
        S["target_pattern"]["sent_count"] = int(S["target_pattern"].get("sent_count", 0)) + 1
        S["target_pattern"]["last_action"] = f"{now_short()} 목표패턴 매수알림 {name_of(sym)} {stage}단계"
    title = f"🟢 매수"
    msg = (
        f"{title}\n"
        f"종목: {name_of(sym)} ({sym})\n"
        f"단계: {stage}차\n"
        f"금액: {fmt_won(amount)}\n"
        f"추천수량: {qty}주\n"
        f"현재가: {fmt_won(price)}\n"
        f"시장: {target_market_regime()}\n"
        f"이유: {reason}\n"
        f"실제 주문: 텔레그램 버튼 90초 유효 / 클릭 시 현재가·조건 재확인"
    )
    url = create_trade_button_url(sym, "BUY", qty, price, reason)
    confirm = confirm_url(sym, "BUY", qty)
    add_alert(msg)
    send_telegram(msg, [[telegram_button(f"🟢 {TELEGRAM_BUTTON_TTL_SEC}초 매수 실행", url)], [telegram_button("확인화면", confirm), telegram_button("📊 대시보드", APP_URL)]])
    write_alert_log("REAL", "target_buy", sym, price, 0, "BUY", reason, True, "telegram")
    return True

def send_real_pattern_sell_alert(sym, qty, reason):
    price = S["prices"].get(sym, 0)
    if qty <= 0:
        qty = int(S["sellable"].get(sym, 0) or S["hold_qty"].get(sym, 0) or 0)
    if qty <= 0:
        return False
    key = f"TARGET_SELL_{today()}_{sym}_{reason}"
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < 300:
            return False
        S["last_alert"][key] = time.time()
        S["target_pattern"]["last_action"] = f"{now_short()} 목표패턴 매도알림 {name_of(sym)}"
    msg = (
        f"🔴 매도\n"
        f"종목: {name_of(sym)} ({sym})\n"
        f"수량: {qty}주\n"
        f"현재가: {fmt_won(price)}\n"
        f"이유: {reason}\n"
        f"실제 주문: 텔레그램 버튼 90초 유효 / 클릭 시 현재가·조건 재확인"
    )
    url = create_trade_button_url(sym, "SELL", qty, price, reason)
    confirm = confirm_url(sym, "SELL", qty)
    add_alert(msg)
    send_telegram(msg, [[telegram_button(f"🔴 {TELEGRAM_BUTTON_TTL_SEC}초 매도 실행", url)], [telegram_button("확인화면", confirm), telegram_button("📊 대시보드", APP_URL)]])
    write_alert_log("REAL", "target_sell", sym, price, 0, "SELL", reason, True, "telegram")
    return True

def run_real_pattern_alert_engine():
    """실계좌 후보 알림 엔진. 최종 최소알림 모드에서는 후보 알림을 보내지 않는다."""
    if FINAL_MINIMAL_ALERT_MODE or not ENABLE_REAL_PATTERN_CANDIDATE_ALERT:
        return
    if not TARGET_PATTERN_ENABLED or not ENABLE_WORK_SWING_ALERT or REAL_ALERT_MODE != "WORK_SWING_ONLY":
        return
    target_pattern_reset_if_new_day()

    # 보유 중이면 매도 알림부터 본다.
    with LOCK:
        watch = dict(S.get("real_watch", {}))
    mode = target_market_regime()
    for sym, item in watch.items():
        qty = int(to_float(item.get("qty", 0)))
        if qty <= 1:
            continue
        price = S["prices"].get(sym, 0)
        buy = to_float(item.get("buy_price", 0))
        high = max(to_float(item.get("high_after_buy", buy)), price)
        if price <= 0 or buy <= 0:
            continue
        profit = pct(price, buy)
        drop = pct(price, high) if high else 0
        if is_after_or_equal_hhmm(DAYTRADE_FORCE_EXIT_TIME):
            send_real_pattern_sell_alert(sym, qty, "15:20 전 당일청산")
        elif profit >= 0.5 and is_after_or_equal_hhmm(NO_NEW_BUY_AFTER) and drop <= -3.0:
            send_real_pattern_sell_alert(sym, qty, f"수익권 고점대비 {drop:.2f}% 이탈")
        elif (not is_inverse_symbol(sym)) and mode == "DOWN":
            send_real_pattern_sell_alert(sym, qty, "롱 보유 중 하락장 전환")
        elif is_inverse_symbol(sym) and mode in ["UP", "RECOVERY"]:
            send_real_pattern_sell_alert(sym, qty, "인버스 보유 중 상승/회복장 전환")

    # 신규/추가 매수 알림
    if buy_time_blocked():
        return
    with LOCK:
        sent_count = int(S.get("target_pattern", {}).get("sent_count", 0))
        active_watch = bool(S.get("real_watch", {}))
    # V4.12: 하루 2번 제한으로 전환장을 막지 않는다.
    # 보유 포지션이 없으면 인버스 1세트 후 레버리지 회복 2세트를 열 수 있도록 최대 4회 허용.
    max_alerts = max(TARGET_MAX_REAL_ALERTS_PER_DAY, WORK_SWING_MAX_REAL_ALERTS_PER_DAY) if POSITION_SET_REENTRY else min(TARGET_MAX_REAL_ALERTS_PER_DAY, WORK_SWING_MAX_REAL_ALERTS_PER_DAY)
    if sent_count >= max_alerts:
        return
    if mode in ["CHOPPY", "NO_TRADE"]:
        # 전체 시장이 애매해도 계열별 회복 후보는 별도 확인한다.
        if not (RECOVERY_CANDIDATE_ENGINE and FAMILY_MODE_ENGINE):
            return

    sym, reason = target_choose_symbol(mode)
    if not sym:
        return
    amount, stage = target_next_stage_amount(sym)
    if amount <= 0:
        return
    send_real_pattern_buy_alert(sym, amount, stage, reason)

# 구 단타 관련 기존 시간 함수는 호환용으로만 남긴다.
def parse_hhmm(s, default_h=15, default_m=20):
    try:
        h, m = str(s).split(":")
        return int(h), int(m)
    except Exception:
        return default_h, default_m

def time_after_hhmm(hhmm):
    h, m = parse_hhmm(hhmm)
    n = now_kst()
    return (n.hour, n.minute) >= (h, m)

def time_before_hhmm(hhmm):
    h, m = parse_hhmm(hhmm)
    n = now_kst()
    return (n.hour, n.minute) < (h, m)

def daytrade_time_open():
    n = now_kst()
    return (n.hour, n.minute) >= (9, 0) and time_before_hhmm(DAYTRADE_CUTOFF)

def load_daytrade_state():
    if not os.path.exists(DAYTRADE_STATE_PATH):
        return
    try:
        with open(DAYTRADE_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        with LOCK:
            if isinstance(data, dict):
                S["daytrade"].update(data)
    except Exception as e:
        set_error(f"단타 state 로드 실패: {e}")

def save_daytrade_state():
    try:
        with LOCK:
            data = dict(S.get("daytrade", {}))
        with open(DAYTRADE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        set_error(f"단타 state 저장 실패: {e}")

def reset_daytrade_if_new_day():
    with LOCK:
        dt = S.get("daytrade", {})
        if dt.get("date") == today():
            return
        # 전일 포지션이 남아 있으면 기록만 남기고 포지션은 유지한다.
        # 실제로는 15:20 전 정산이 원칙이라 남아 있으면 다음 루프에서 강제정리 알림이 뜬다.
        dt["date"] = today()
        dt["trade_count"] = 0
        dt["pending"] = None
        dt["market_mode"] = "대기"
        dt["last_action"] = "새 거래일 시작"
        if not dt.get("cash"):
            dt["cash"] = DAYTRADE_BASE_CASH
        S["daytrade"] = dt
    save_daytrade_state()

def is_locked_recovery_symbol(sym):
    # 현재 물려 있는 하이닉스 레버리지 보유분은 복구용이므로 단타에서 제외.
    # 복구 후 보유가 사라지면 다시 후보가 될 수 있다.
    try:
        return str(sym) == LEV and to_float(S["hold_qty"].get(LEV, 0)) > 0
    except Exception:
        return False

def daytrade_available_cash():
    with LOCK:
        cash = to_int(S["daytrade"].get("cash", DAYTRADE_BASE_CASH))
        real_cash = to_int(S.get("cash", 0))
    # 실계좌 매수가능금액보다 많이 쓰지 않게 제한
    if real_cash > 0:
        return min(cash, real_cash)
    return cash

def daytrade_market_mode():
    """OPERATING V4 공통 시장상태를 단타 엔진에서도 그대로 사용한다."""
    return operating_market_mode()

def daytrade_candidate_for_mode(mode):
    # CHOPPY/NO_TRADE에서는 실행 후보 없음. 관찰만.
    if mode in ["CHOPPY", "NO_TRADE"]:
        return None
    if mode == "SEMI_LEADER_UP":
        return choose_best_symbol(SEMI_LONG_SYMBOLS)
    if mode == "UP":
        return choose_best_symbol(UP_LONG_SYMBOLS)
    if mode == "DOWN":
        if semiconductor_strong():
            return None
        return choose_best_symbol(INVERSE_SYMBOLS)
    return None

def daytrade_calc_qty(sym):
    price = S["prices"].get(sym, 0)
    cash = daytrade_available_cash()
    if price <= 0 or cash <= 0:
        return 0
    return int((cash * ORDER_SAFE_RATIO) // price)

def daytrade_position_profit(pos, current_price):
    entry = to_float(pos.get("entry_price", 0))
    if entry <= 0:
        return 0.0
    return pct(current_price, entry)

def daytrade_make_signal(action, sym, reason):
    signal_id = f"DT{int(time.time()*1000)}{uuid.uuid4().hex[:5]}"
    price = S["prices"].get(sym, 0)
    qty = daytrade_calc_qty(sym)
    pending = {
        "id": signal_id,
        "action": action,
        "symbol": sym,
        "name": name_of(sym),
        "price": price,
        "qty": qty,
        "reason": reason,
        "created": now_text(),
    }
    with LOCK:
        S["daytrade"]["pending"] = pending
    save_daytrade_state()
    return pending

def daytrade_exec_url(action, signal_id):
    base = APP_URL or ""
    qs = urlencode({"action": action, "signal": signal_id, "token": DAYTRADE_EXEC_TOKEN})
    return f"{base}/daytrade_exec?{qs}" if base else "/daytrade_exec?" + qs

def daytrade_send_button(pending):
    if not pending:
        return
    action = pending.get("action", "")
    sym = pending.get("symbol", "")
    price = to_float(pending.get("price", 0))
    qty = int(to_float(pending.get("qty", 0)))
    reason = pending.get("reason", "")
    mode = S["daytrade"].get("market_mode", "")
    if action == "BUY":
        title = "🟢 [매수-실행] 단타/스윙 후보"
        btn_title = "🟢 매수 실행"
    elif action == "SELL":
        title = "🔴 [매도-실행] 보유 정리"
        btn_title = "🔴 매도 실행"
    else:
        title = "🟢 [인버스-실행] 하락장 단타"
        btn_title = "🟢 인버스 실행"

    msg = (
        f"{title}\n"
        f"시장상태: {mode}\n"
        f"종목: {name_of(sym)} ({sym})\n"
        f"현재가: {fmt_won(price)}\n"
        f"수량: {qty}주\n"
        f"단타시드: {fmt_won(S['daytrade'].get('cash', DAYTRADE_BASE_CASH))}\n"
        f"이유: {reason}\n"
        f"원칙: 15:20 전 정산 / 수익 재투자"
    )
    url = daytrade_exec_url(action, pending["id"])
    add_alert(msg)

    # URL 버튼을 누르면 /daytrade_exec 가 주문을 실행한다.
    # DAYTRADE_EXEC_TOKEN이 비어 있으면 실행은 차단된다.
    send_telegram(msg, [[telegram_button(btn_title, url)], [telegram_button("📊 대시보드", APP_URL or url)]])

def daytrade_alert_once(key, pending, cooldown=None):
    cooldown = cooldown or DAYTRADE_ALERT_COOLDOWN_SEC
    with LOCK:
        last = S["last_alert"].get(key, 0)
        if time.time() - last < cooldown:
            return
        S["last_alert"][key] = time.time()
    daytrade_send_button(pending)

def daytrade_open_position(action, sym, qty, price):
    side = "BUY"
    result = place_order_manual(sym, side, qty)
    if not result.get("ok"):
        return result
    pos = {
        "symbol": sym,
        "name": name_of(sym),
        "qty": qty,
        "entry_price": price,
        "entry_time": now_text(),
        "highest_price": price,
        "lowest_price": price,
        "action": action,
    }
    with LOCK:
        S["daytrade"]["position"] = pos
        S["daytrade"]["trade_count"] = int(S["daytrade"].get("trade_count", 0)) + 1
        S["daytrade"]["last_action"] = f"{now_short()} 단타 진입 {name_of(sym)}"
        S["daytrade"]["pending"] = None
    save_daytrade_state()
    return {"ok": True, "message": f"단타 매수 실행: {name_of(sym)} {qty}주"}

def daytrade_close_position(reason="단타 청산"):
    with LOCK:
        pos = S["daytrade"].get("position")
    if not pos:
        return {"ok": False, "message": "단타 포지션 없음"}
    sym = pos.get("symbol")
    qty = int(to_float(pos.get("qty", 0)))
    cur = S["prices"].get(sym, 0)
    if qty <= 0 or cur <= 0:
        return {"ok": False, "message": "수량 또는 현재가 없음"}
    result = place_order_manual(sym, "SELL", qty)
    if not result.get("ok"):
        return result

    pnl_pct = daytrade_position_profit(pos, cur)
    cash_after = int(qty * cur)
    trade_row = {
        "time": now_text(),
        "symbol": sym,
        "name": name_of(sym),
        "qty": qty,
        "entry_price": pos.get("entry_price"),
        "exit_price": cur,
        "pnl_pct": round(pnl_pct, 2),
        "cash_after": cash_after,
        "reason": reason,
    }
    with LOCK:
        S["daytrade"]["cash"] = cash_after
        S["daytrade"]["position"] = None
        S["daytrade"]["pending"] = None
        S["daytrade"]["last_action"] = f"{now_short()} 단타 청산 {pnl_pct:.2f}%"
        S["daytrade"]["trades"].insert(0, trade_row)
        S["daytrade"]["trades"] = S["daytrade"]["trades"][:50]
    write_row(os.path.join(day_dir(), f"daytrade_trades_{today()}.csv"),
              ["time","symbol","name","qty","entry_price","exit_price","pnl_pct","cash_after","reason"],
              trade_row)
    save_daytrade_state()
    return {"ok": True, "message": f"단타 매도 완료: {name_of(sym)} {pnl_pct:.2f}% / 시드 {fmt_won(cash_after)}"}

def run_daytrade_engine():
    # 구 구 단타 단타 엔진은 V4.10에서 제거.
    return

def execute_daytrade_from_url(qs):
    return {"ok": False, "message": "구 구 단타 단타 실행 URL은 V4.10에서 제거되었습니다. 텔레그램 🟢/🔴 목표패턴 확인 버튼을 사용하세요."}

def record_order(row):
    with LOCK:
        S["orders"].insert(0, row)
        S["orders"] = S["orders"][:80]
    write_row(orders_path(), ["time", "symbol", "name", "side", "qty", "status", "response"], row)

def place_order_manual(sym, side, qty):
    if PAPER_ONLY_MODE:
        return {"ok": False, "message": "PAPER_ONLY_MODE=true: 실제 주문 완전 차단"}
    if sym in REAL_ORDER_BLOCKED_SYMBOLS:
        return {"ok": False, "message": f"보호종목 {sym}: 실제 매수·매도 모두 차단"}
    gate_ok, gate_reason = market_safety_gate(sym)
    if not gate_ok:
        return {"ok": False, "message": f"시장 안전게이트 차단: {gate_reason}"}
    if sym not in ALL:
        return {"ok": False, "message": "허용되지 않은 종목"}
    if side not in ["BUY", "SELL"]:
        return {"ok": False, "message": "BUY/SELL 오류"}
    qty = to_int(qty)
    if qty <= 0:
        return {"ok": False, "message": "수량이 0입니다."}
    if side == "SELL":
        # 실제 매도 실행 직전에는 해당 종목 1개만 실시간 재조회한다.
        # 평소 26개 전체 조회는 하지 않는다.
        sellable = int(get_sellable_quantity(sym, force=True))
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
    if ENABLE_REAL_ORDER_RESULT_ALERT:
        send_kakao(("✅" if ok else "⚠️") + f" 실계좌 반자동 {side_kr}\n{name_of(sym)}\n수량: {qty}주\n결과: {row['status']}", APP_URL)
    refresh_account_all(force=True)
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

def record_paper(action, sym, price, qty, reason, pl=0, strategy="", mode="", source="AUTO"):
    update_paper_asset()
    with LOCK:
        row = {
            "time": now_short(),
            "source": source,
            "strategy": strategy,
            "market_mode": mode or S.get("daytrade", {}).get("market_mode", ""),
            "action": action,
            "symbol": sym,
            "name": name_of(sym),
            "price": price,
            "qty": qty,
            "pl": pl,
            "reason": reason,
            "asset": S["paper"].get("asset", 0),
        }
        S["paper"]["trades"].insert(0, row)
        S["paper"]["trades"] = S["paper"]["trades"][:100]
    write_row(paper_path(), ["time", "source", "strategy", "market_mode", "action", "symbol", "name", "price", "qty", "pl", "reason", "asset"], row)
    save_state()

def paper_invested_amount():
    with LOCK:
        positions = dict(S["paper"].get("positions", {}))
        prices = dict(S["prices"])
    total = 0
    for sym, pos in positions.items():
        total += to_float(pos.get("qty", 0)) * prices.get(sym, to_float(pos.get("avg", 0)))
    return int(total)

def paper_buy_amount(sym, amount, reason, strategy="SWING", mode=""):
    if sym not in ALL:
        return False
    price = S["prices"].get(sym, 0)
    if price <= 0 or amount <= 0:
        return False
    with LOCK:
        cash = to_int(S["paper"].get("cash", 0))
    # 가상도 실제 운영처럼 최소 방어현금은 남긴다.
    spendable = max(0, cash - MIN_DEFENSE_CASH)
    amount = min(int(amount), spendable)
    if amount <= 0:
        return False
    qty = int(amount // price)
    if qty <= 0:
        return False
    cost = qty * price
    with LOCK:
        pos = S["paper"]["positions"].get(sym, {"qty": 0, "avg": 0, "stage": 0, "strategy": strategy})
        old_qty = to_float(pos.get("qty", 0))
        old_avg = to_float(pos.get("avg", 0))
        new_qty = old_qty + qty
        new_avg = ((old_qty * old_avg) + cost) / new_qty if new_qty else price
        stage = min(3, int(to_float(pos.get("stage", 0))) + 1)
        S["paper"]["cash"] -= cost
        S["paper"]["positions"][sym] = {
            "qty": new_qty,
            "avg": new_avg,
            "buy_time": pos.get("buy_time") or now_text(),
            "high_after_buy": max(to_float(pos.get("high_after_buy", 0)), price, new_avg),
            "stage": stage,
            "strategy": strategy,
        }
        S["paper"]["last_action"] = f"{now_short()} AI 자동가상매수 {name_of(sym)} {stage}단계"
    record_paper("AI자동가상매수", sym, price, qty, reason, strategy=strategy, mode=mode or operating_market_mode(), source="AUTO")
    return True

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
    record_paper("수동가상매수", sym, price, qty, reason, strategy="MANUAL", mode=operating_market_mode(), source="MANUAL")
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
    record_paper("수동가상매도", sym, price, qty, reason, pl, strategy="MANUAL", mode=operating_market_mode(), source="MANUAL")
    return True

def run_paper_ai_if_enabled():
    """AI 가상계좌 자동운영.
    ENABLE_PAPER_AUTO=true 이면 사용자가 버튼을 누르지 않아도 2천만원 기준으로
    AI가 스스로 단타/스윙/관망/인버스를 판단해 가상매수/가상매도한다.

    중요:
    - 데이터 저장은 계속 한다.
    - AI 가상계좌가 돈을 움직이는 시간은 PAPER_AUTO_START~PAPER_AUTO_END 안에서만 허용한다.
    - 장 마감/정산 시간 이후에는 가상매수/가상매도/가상관망 로그를 새로 만들지 않는다.
    """
    mode = target_market_regime()
    with LOCK:
        S["daytrade"]["market_mode"] = mode

    if not ENABLE_PAPER_AUTO:
        update_paper_asset()
        return

    # 장중 자동운영 시간 밖이면 아무 매매도 하지 않는다.
    # 이미 저장된 가격/CSV/대시보드 갱신은 루프의 write_logs()가 계속 담당한다.
    if not paper_auto_time_open():
        update_paper_asset()
        return

    with LOCK:
        positions = dict(S["paper"].get("positions", {}))
        prices = dict(S["prices"])

    # 1) 보유 포지션 자동 매도/보유/추가매수 판단
    for sym, pos in list(positions.items()):
        price = prices.get(sym, 0)
        avg = to_float(pos.get("avg", 0))
        if price <= 0 or avg <= 0:
            continue
        high = max(to_float(pos.get("high_after_buy", avg)), price)
        stage = int(to_float(pos.get("stage", 1)))
        strategy = pos.get("strategy", "SWING")
        with LOCK:
            if sym in S["paper"]["positions"]:
                S["paper"]["positions"][sym]["high_after_buy"] = high
        profit = pct(price, avg)
        drop = pct(price, high) if high else 0

        sell_reason = ""
        if profit <= -3.0:
            sell_reason = f"AI 자동 손절 {profit:.2f}%"
        elif is_inverse_symbol(sym) and mode in ["UP", "SEMI_LEADER_UP"]:
            sell_reason = "AI 자동매도: 인버스 보유 중 상승/반도체 주도 전환"
        elif (not is_inverse_symbol(sym)) and mode == "DOWN":
            sell_reason = "AI 자동매도: 롱 보유 중 DOWN 전환"
        elif is_after_or_equal_hhmm(NO_NEW_BUY_AFTER) and profit >= 1.0 and drop <= -1.5:
            sell_reason = f"AI 자동 수익보호: 14:30 이후 고점대비 {drop:.2f}%"
        elif profit >= 1.0 and drop <= -3.0:
            sell_reason = f"AI 자동 추적익절: 고점대비 {drop:.2f}%"
        elif strategy == "DAYTRADE" and time_after_hhmm(DAYTRADE_FORCE_EXIT_TIME):
            sell_reason = "AI 자동 단타 15:20 전 정리"

        if sell_reason:
            paper_sell(sym, 1.0, sell_reason)
            continue

        # 스윙 포지션은 반도체 주도/상승장이 유지되고 최대금액 전이면 단계적 추가매수.
        # 단, 14:30 이후 신규/추가 가상매수는 금지한다.
        invested = paper_invested_amount()
        if (not buy_time_blocked()) and strategy == "SWING" and mode in ["SEMI_LEADER_UP", "UP"] and stage < 3 and invested < SWING_MAX_EXPOSURE:
            if profit >= 0.5 or symbol_strength(sym) >= 72:
                next_amount = SWING_BUY_STEP_AMOUNTS[min(stage, 2)]
                paper_buy_amount(sym, next_amount, f"AI 자동 추가매수 {stage+1}단계: {mode} 강세 유지", strategy="SWING", mode=mode)

    with LOCK:
        has = bool(S["paper"].get("positions"))
    if has:
        update_paper_asset()
        save_state()
        return

    # 2) 신규 자동진입 판단
    if buy_time_blocked():
        record_paper_wait_once("09:05 전 또는 14:30 이후 신규 가상매수 금지", mode)
        update_paper_asset()
        return
    if mode in ["CHOPPY", "NO_TRADE"]:
        record_paper_wait_once(f"{mode}: 방향 없음, 가상매수 안 함", mode)
        update_paper_asset()
        return

    if mode == "SEMI_LEADER_UP":
        sym = choose_best_symbol(SEMI_LONG_SYMBOLS)
        if sym:
            paper_buy_amount(sym, SWING_BUY_STEP_AMOUNTS[0], f"AI 자동 스윙 1차: 반도체 주도장 {sym}", strategy="SWING", mode=mode)
    elif mode == "UP":
        sym = choose_best_symbol(UP_LONG_SYMBOLS)
        if sym:
            paper_buy_amount(sym, SWING_BUY_STEP_AMOUNTS[0], f"AI 자동 롱 1차: 상승장 {sym}", strategy="SWING", mode=mode)
    elif mode == "DOWN":
        if not semiconductor_strong():
            sym = choose_best_symbol(INVERSE_SYMBOLS)
            if sym:
                paper_buy_amount(sym, min(5_000_000, INVERSE_MAX_EXPOSURE), f"AI 자동 인버스 단타: DOWN {sym}", strategy="DAYTRADE", mode=mode)

    update_paper_asset()
    save_state()

# ============================================================
# SHADOW FIXED V1 실전가정 가상체결 엔진
# ============================================================

def _shadow_default_state(cash=None):
    start = int(cash if cash is not None else SHADOW_FIXED_START_CASH)
    return {
        "date": today(),
        "strategy_id": SHADOW_FIXED_STRATEGY_ID,
        "start_cash": start,
        "cash": start,
        "position": None,
        "realized_pl": 0,
        "asset": start,
        "profit_rate": 0,
        "checkpoints": {},
        "inv_evaluated": False,
        "lev_evaluated": False,
        "inv_signal": False,
        "lev_signal": False,
        "stopped_today": False,
        "summary_saved": False,
        "last_action": "일일 초기화",
        "trades": [],
    }


def _shadow_ensure_strategy_state():
    """전략 버전이 바뀌면 과거 엔진 자산과 섞지 않고 1,000만원으로 새로 시작."""
    with LOCK:
        st = S.get("shadow_fixed")
        if not isinstance(st, dict) or st.get("strategy_id") != SHADOW_FIXED_STRATEGY_ID:
            S["shadow_fixed"] = _shadow_default_state(SHADOW_FIXED_START_CASH)
            changed = True
        else:
            # 구 state.json에 새 필드가 없어도 안전하게 보완
            st.setdefault("stopped_today", False)
            st.setdefault("summary_saved", False)
            st.setdefault("strategy_id", SHADOW_FIXED_STRATEGY_ID)
            changed = False
    if changed:
        save_state()


def _shadow_roll_date():
    """날짜가 바뀌어도 누적 현금은 유지하고 일일 판정 플래그만 초기화."""
    _shadow_ensure_strategy_state()
    with LOCK:
        st = S.get("shadow_fixed") or _shadow_default_state()
        if st.get("date") == today():
            return
        carry_cash = int(to_float(st.get("cash", SHADOW_FIXED_START_CASH)))
        # 비정상적으로 전일 포지션이 남으면 현재가로 강제 정리해 누적자산을 보존한다.
        pos = st.get("position")
        if isinstance(pos, dict):
            sym = str(pos.get("symbol", ""))
            qty = int(to_float(pos.get("qty", 0)))
            px = to_float(S.get("prices", {}).get(sym, pos.get("entry_price", 0)))
            if qty > 0 and px > 0:
                gross = qty * px
                fee = int(round(gross * SHADOW_FEE_SIDE_PCT / 100))
                carry_cash += int(gross - fee)
        start_cash = int(to_float(st.get("start_cash", SHADOW_FIXED_START_CASH)))
        fresh = _shadow_default_state(carry_cash)
        fresh["start_cash"] = start_cash
        fresh["cash"] = carry_cash
        fresh["asset"] = carry_cash
        fresh["profit_rate"] = pct(carry_cash, start_cash) if start_cash else 0
        S["shadow_fixed"] = fresh
    save_state()


def _shadow_checkpoint(hhmm, sym):
    """해당 분 안에서 마지막 수집가격을 계속 덮어써 1분 종가처럼 고정."""
    n = now_kst()
    if n.strftime("%H:%M") != hhmm:
        return
    price = to_float(S.get("prices", {}).get(sym, 0))
    if price <= 0:
        return
    key = f"{sym}_{hhmm}"
    with LOCK:
        S["shadow_fixed"].setdefault("checkpoints", {})[key] = {
            "price": price,
            "captured_at": now_text(),
        }


def _shadow_get_checkpoint(sym, hhmm):
    key = f"{sym}_{hhmm}"
    with LOCK:
        item = S.get("shadow_fixed", {}).get("checkpoints", {}).get(key, {})
    return to_float(item.get("price", 0)) if isinstance(item, dict) else 0


def _shadow_update_asset():
    with LOCK:
        st = S["shadow_fixed"]
        cash = to_float(st.get("cash", 0))
        pos = st.get("position")
        total = cash
        if isinstance(pos, dict):
            sym = str(pos.get("symbol", ""))
            qty = to_float(pos.get("qty", 0))
            px = to_float(S.get("prices", {}).get(sym, pos.get("entry_price", 0)))
            total += qty * px
        st["asset"] = int(total)
        start = to_float(st.get("start_cash", SHADOW_FIXED_START_CASH))
        st["profit_rate"] = pct(total, start) if start else 0


def _shadow_write_signal(kind, sym, move_pct, passed, reason):
    row = {
        "time": now_text(),
        "strategy": SHADOW_FIXED_STRATEGY_ID,
        "kind": kind,
        "symbol": sym,
        "name": name_of(sym),
        "move_pct": round(move_pct, 4),
        "passed": bool(passed),
        "reason": reason,
        "real_order": False,
    }
    write_row(
        shadow_fixed_signal_path(),
        ["time", "strategy", "kind", "symbol", "name", "move_pct", "passed", "reason", "real_order"],
        row,
    )


def _shadow_record(action, sym, price, qty, pl, reason, fee=0):
    _shadow_update_asset()
    with LOCK:
        st = S["shadow_fixed"]
        row = {
            "time": now_text(),
            "strategy": SHADOW_FIXED_STRATEGY_ID,
            "action": action,
            "symbol": sym,
            "name": name_of(sym),
            "price": round(to_float(price), 2),
            "qty": int(qty),
            "fee": int(fee),
            "pl": int(pl),
            "cash": int(to_float(st.get("cash", 0))),
            "asset": int(to_float(st.get("asset", 0))),
            "profit_rate": round(to_float(st.get("profit_rate", 0)), 4),
            "reason": reason,
            "real_order": False,
        }
        st.setdefault("trades", []).insert(0, row)
        st["trades"] = st["trades"][:100]
        st["last_action"] = f"{now_short()} {action} {name_of(sym)}"
    write_row(
        shadow_fixed_path(),
        ["time", "strategy", "action", "symbol", "name", "price", "qty", "fee", "pl", "cash", "asset", "profit_rate", "reason", "real_order"],
        row,
    )
    save_state()






def _ranking_result(data):
    if not isinstance(data, dict):
        return {}, []
    result = data.get("result")
    if not isinstance(result, dict):
        return {}, []
    rankings = result.get("rankings")
    if not isinstance(rankings, list):
        rankings = []
    return result, rankings


def _ranking_change_pct(item):
    price = item.get("price") if isinstance(item, dict) else {}
    if not isinstance(price, dict):
        return 0.0
    # 토스 API changeRate는 0.0125 = 1.25% 형식이다.
    return to_float(price.get("changeRate"), 0.0) * 100.0


def _ranking_last_price(item):
    price = item.get("price") if isinstance(item, dict) else {}
    if not isinstance(price, dict):
        return 0.0
    return to_float(price.get("lastPrice"), 0.0)


def _stock_info_map(symbols):
    """랭킹 후보의 종목명·시장·상장상태를 최대 200개 단위로 보강한다."""
    result = {}
    clean = [str(x).strip() for x in symbols if str(x).strip()]
    for i in range(0, len(clean), 200):
        batch = clean[i:i+200]
        code, data = api_get("/api/v1/stocks", params={"symbols": ",".join(batch)}, timeout=15)
        if code != 200:
            continue
        for item in first_list(data):
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or "").strip()
            if not sym:
                continue
            result[sym] = {
                "symbol": sym,
                "name": str(item.get("name") or sym).strip(),
                "market": str(item.get("market") or "").strip(),
                "security_type": str(item.get("securityType") or "").strip(),
                "currency": str(item.get("currency") or "").strip(),
                "listing_status": str(item.get("status") or "").strip(),
                "trading_suspended": bool(
                    (item.get("koreanMarketDetail") or {}).get("krxTradingSuspended")
                    if isinstance(item.get("koreanMarketDetail"), dict)
                    else False
                ),
            }
    return result


def load_full_market_universe(force=False):
    """토스 랭킹 API로 현재 시장 후보군을 자동 구성한다.

    전체 상장종목 마스터를 빈 symbols로 요청하지 않는다.
    시장 거래대금·거래량·상승·하락 랭킹을 합쳐 G01~G05 후보군으로 사용한다.
    """
    state = S.setdefault("full_market", {})
    now_ts = time.time()

    if (
        state.get("universe")
        and not force
        and now_ts - to_float(state.get("stock_master_checked_at", 0)) < FULL_MARKET_SCAN_INTERVAL_SEC
    ):
        return state["universe"]

    merged = {}
    errors = []
    ranked_at_values = []

    for ranking_type in FULL_MARKET_RANKING_TYPES:
        duration = "1d" if ranking_type in {"TOP_GAINERS", "TOP_LOSERS"} else "realtime"
        params = {
            "type": ranking_type,
            "marketCountry": "KR",
            "duration": duration,
            "excludeInvestmentCaution": True,
            "count": max(1, min(100, FULL_MARKET_RANKING_COUNT)),
        }
        code, data = api_get("/api/v1/rankings", params=params, timeout=15)
        if code != 200:
            errors.append(f"{ranking_type}:HTTP_{code}")
            continue

        result, rankings = _ranking_result(data)
        ranked_at = str(result.get("rankedAt") or "")
        if ranked_at:
            ranked_at_values.append(ranked_at)

        for item in rankings:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or "").strip()
            if not sym or sym in FULL_MARKET_BLOCKED_SYMBOLS:
                continue
            currency = str(item.get("currency") or "").upper()
            if currency and currency != "KRW":
                continue

            row = merged.setdefault(sym, {
                "symbol": sym,
                "name": sym,
                "market": "",
                "security_type": "",
                "currency": currency or "KRW",
                "listing_status": "",
                "ranking_types": [],
                "ranking_best": {},
                "price": 0.0,
                "change_pct": 0.0,
                "volume": 0.0,
                "turnover": 0.0,
                "timestamp": ranked_at,
            })
            row["ranking_types"].append(ranking_type)
            row["ranking_best"][ranking_type] = int(to_float(item.get("rank"), 9999))
            row["price"] = max(to_float(row.get("price"), 0), _ranking_last_price(item))
            row["change_pct"] = _ranking_change_pct(item)
            row["volume"] = max(to_float(row.get("volume"), 0), to_float(item.get("tradingVolume"), 0))
            row["turnover"] = max(to_float(row.get("turnover"), 0), to_float(item.get("tradingAmount"), 0))
            if ranked_at:
                row["timestamp"] = ranked_at

    symbols = list(merged)
    info_map = _stock_info_map(symbols)
    universe = {}

    for sym, row in merged.items():
        info = info_map.get(sym, {})
        if info:
            if str(info.get("currency") or "KRW").upper() != "KRW":
                continue
            if str(info.get("listing_status") or "ACTIVE").upper() not in {"ACTIVE", ""}:
                continue
            if info.get("trading_suspended"):
                continue
            row.update(info)
        if to_float(row.get("price"), 0) < FULL_MARKET_MIN_PRICE:
            continue
        if to_float(row.get("turnover"), 0) and to_float(row.get("turnover"), 0) < FULL_MARKET_MIN_TURNOVER:
            continue
        universe[sym] = row

    state["universe"] = universe
    state["stock_master_checked_at"] = now_ts
    state["stock_master_source"] = "TOSS_/api/v1/rankings"
    state["ranking_last_at"] = max(ranked_at_values) if ranked_at_values else ""
    state["ranking_errors"] = errors
    state["status"] = (
        f"토스 전체시장 랭킹 후보 {len(universe):,}개 로드"
        if universe
        else "FULL_MARKET_UNIVERSE_EMPTY / " + (", ".join(errors) if errors else "RANKINGS_EMPTY")
    )
    return universe


def _quote_field(item, keys, default=0.0):
    for k in keys:
        if k in item:
            return to_float(item.get(k), default)
    return default


def scan_full_market_universe(force=False):
    """토스 전체시장 랭킹 후보를 실시간 가격으로 보강해 3그룹 순위를 만든다."""
    state = S.setdefault("full_market", {})
    if not ENABLE_FULL_MARKET_SCANNER:
        state["status"] = "전체시장 스캐너 OFF"
        return False
    if not force and time.time() - to_float(state.get("last_scan_ts", 0)) < FULL_MARKET_SCAN_INTERVAL_SEC:
        return bool(state.get("ranked"))

    universe = load_full_market_universe(force)
    symbols = list(universe)
    state["last_scan_ts"] = time.time()
    state["last_scan_text"] = now_text()

    if not symbols:
        state["status"] = "FULL_MARKET_UNIVERSE_EMPTY"
        return False

    # 랭킹 후보만 현재가 다건조회한다. 공식 최대 200개 제한을 지킨다.
    quote_map = {}
    for i in range(0, len(symbols), 200):
        batch = symbols[i:i+200]
        code, data = api_get("/api/v1/prices", params={"symbols": ",".join(batch)}, timeout=15)
        if code != 200:
            state["errors"] = int(state.get("errors", 0)) + 1
            continue
        for item in first_list(data):
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or "").strip()
            if sym:
                quote_map[sym] = item

    for sym, base in universe.items():
        item = quote_map.get(sym, {})
        price = _quote_field(item, ["lastPrice", "price", "currentPrice", "closePrice", "tradePrice"], to_float(base.get("price"), 0))
        if price < FULL_MARKET_MIN_PRICE:
            continue

        ts = str(item.get("timestamp") or base.get("timestamp") or "")
        api_dt = parse_api_datetime(ts)
        if ENABLE_MARKET_SAFETY_GATE and api_dt and api_dt.strftime("%Y-%m-%d") != today():
            continue

        prev = state.setdefault("quotes", {}).get(sym, {})
        prev_price = to_float(prev.get("price"), price)
        short_mom = pct(price, prev_price) if prev_price else 0.0

        q = {
            **base,
            "price": price,
            "short_mom": short_mom,
            "timestamp": ts,
            "saved_at": now_text(),
        }
        state["quotes"][sym] = q
        S.setdefault("prices", {})[sym] = price
        S.setdefault("market_data_capture", {}).setdefault("price_timestamp", {})[sym] = ts

        hist = S.setdefault("history", {}).setdefault(sym, [])
        hist.append(price)
        if len(hist) > TARGET_PATTERN_LOOKBACK_POINTS:
            del hist[:-TARGET_PATTERN_LOOKBACK_POINTS]
        S.setdefault("high", {})[sym] = max(to_float(S.get("high", {}).get(sym, price)), price)
        old_low = to_float(S.get("low", {}).get(sym, price)) or price
        S.setdefault("low", {})[sym] = min(old_low, price)

    ranked = []
    for sym, q in state.get("quotes", {}).items():
        if sym not in universe or sym in FULL_MARKET_BLOCKED_SYMBOLS:
            continue
        if data_age_seconds(q.get("timestamp")) > max(MAX_PRICE_AGE_SEC, FULL_MARKET_SCAN_INTERVAL_SEC * 3):
            continue

        turnover = to_float(q.get("turnover"), 0)
        volume = to_float(q.get("volume"), 0)
        change_pct = to_float(q.get("change_pct"), 0)
        short_mom = to_float(q.get("short_mom"), 0)
        ranks = q.get("ranking_best") if isinstance(q.get("ranking_best"), dict) else {}

        amount_rank = int(ranks.get("MARKET_TRADING_AMOUNT", 9999))
        volume_rank = int(ranks.get("MARKET_TRADING_VOLUME", 9999))
        gainer_rank = int(ranks.get("TOP_GAINERS", 9999))
        loser_rank = int(ranks.get("TOP_LOSERS", 9999))

        rank_bonus = 0.0
        for r, weight in [(amount_rank, 28.0), (volume_rank, 18.0), (gainer_rank, 16.0), (loser_rank, 8.0)]:
            if r <= 100:
                rank_bonus += weight * (101 - r) / 100.0

        score = (
            rank_bonus
            + min(28.0, max(-28.0, change_pct * 2.2))
            + min(20.0, max(-20.0, short_mom * 16.0))
            + min(18.0, (max(0.0, turnover) ** 0.5) / 24000.0)
            + min(6.0, (max(0.0, volume) ** 0.5) / 2500.0)
        )
        ranked.append((score, sym, q))

    ranked.sort(key=lambda x: x[0], reverse=True)
    state["ranked"] = ranked[:FULL_MARKET_TOP_N]
    state["status"] = (
        f"토스 랭킹시장 후보 {len(universe):,}개, 실시간가격 {len(quote_map):,}개, 최종 {len(state['ranked'])}개"
    )
    return bool(state["ranked"])


def ensure_live_orderbook(sym):
    """3그룹이 선택한 종목의 호가를 주문 직전에 즉시 조회한다."""
    state = S.setdefault("market_data_capture", {})
    ob = state.setdefault("latest_orderbook", {}).get(sym,{})
    if data_age_seconds(ob.get("timestamp")) <= MAX_ORDERBOOK_AGE_SEC and to_float(ob.get("best_ask",0)) > 0:
        return True
    code, data = api_get("/api/v1/orderbook", params={"symbol":sym}, timeout=8)
    if code != 200:
        return False
    result = _result_dict(data)
    asks = result.get("asks",[]) if isinstance(result,dict) and isinstance(result.get("asks",[]),list) else []
    bids = result.get("bids",[]) if isinstance(result,dict) and isinstance(result.get("bids",[]),list) else []
    ts = str(result.get("timestamp","")) if isinstance(result,dict) else ""
    state["latest_orderbook"][sym] = {
        "timestamp":ts,
        "best_ask":to_float(asks[0].get("price",0)) if asks else 0,
        "best_bid":to_float(bids[0].get("price",0)) if bids else 0,
        "asks":asks, "bids":bids,
    }
    return bool(asks and bids)


def full_market_candidate(ai_id):
    """G01~G05가 서로 다른 방식으로 전체시장 후보를 고른다."""
    scan_full_market_universe(False)
    ranked = list(S.setdefault("full_market",{}).get("ranked",[]))
    scored = []
    for base_score,sym,q in ranked:
        hist = list(S.get("history",{}).get(sym,[]) or [])
        cur = to_float(q.get("price",0))
        if cur <= 0:
            continue
        def move(n):
            return pct(cur,to_float(hist[-n-1])) if len(hist)>n and to_float(hist[-n-1])>0 else 0.0
        r3,r10 = move(3),move(10)
        high = max([to_float(x) for x in hist[-30:] if to_float(x)>0] or [cur])
        low = min([to_float(x) for x in hist[-30:] if to_float(x)>0] or [cur])
        from_high,from_low = pct(cur,high),pct(cur,low)
        turnover = to_float(q.get("turnover",0))
        liquidity = min(30.0,(max(turnover,0.0)**0.5)/20000.0)
        if ai_id=="G01":
            metric = base_score + liquidity + r3*8
        elif ai_id=="G02":
            metric = liquidity + r3*16 + r10*8 + (12 if from_high>=-0.3 else -10)
        elif ai_id=="G03":
            metric = liquidity + from_low*7 + r3*10 if -4.0<=from_high<=-0.3 and r3>0 else -999
        elif ai_id=="G04":
            metric = liquidity + from_low*9 + r3*14 if from_low>=1.0 and r10<0 else -999
        else:
            metric = base_score*0.45 + liquidity + r3*10 + r10*6 - abs(from_high)*1.5
        scored.append((metric,sym,base_score,r3,r10,from_high,from_low,liquidity))
    return max(scored,default=(0,"",0,0,0,0,0,0),key=lambda x:x[0])


def multi_ai_path(ai_id):
    return os.path.join(day_dir(), f"paper_ai_{ai_id}_{today()}.csv")


def _multi_ai_default(ai_id):
    return {
        "id": ai_id,
        "name": MULTI_AI_NAMES.get(ai_id, ai_id),
        "start_cash": MULTI_AI_START_CASH,
        "cash": MULTI_AI_START_CASH,
        "positions": {},
        "realized_pl": 0,
        "asset": MULTI_AI_START_CASH,
        "profit_rate": 0.0,
        "trades": [],
        "last_action": "초기화",
        "last_decision_ts": 0,
         "last_decision_date": "",
        "group": MULTI_AI_GROUP.get(ai_id, ""),
        "universe_type": MULTI_AI_UNIVERSE.get(ai_id, ""),
        "parent_strategy": MULTI_AI_PARENT.get(ai_id, ai_id),
        "mdd_pct": 0.0,
        "peak_asset": MULTI_AI_START_CASH,
        "loss_streak": 0,
        "decision_data_end": "",
        "combo_date": "",
        "combo_phase": 0,
        "combo_last_symbol": "",
    }


def ensure_multi_ai_states():
    with LOCK:
        states = S.setdefault("paper_ais", {})
        for ai_id in MULTI_AI_IDS:
            cur = states.get(ai_id)
            if not isinstance(cur, dict):
                states[ai_id] = _multi_ai_default(ai_id)
                continue
            default = _multi_ai_default(ai_id)
            for k, v in default.items():
                cur.setdefault(k, v)
            cur["id"] = ai_id
            cur["name"] = MULTI_AI_NAMES.get(ai_id, ai_id)
            cur.setdefault("positions", {})
            cur.setdefault("trades", [])


def _multi_ai_asset(ai_id):
    ensure_multi_ai_states()
    with LOCK:
        st = S["paper_ais"][ai_id]
        total = to_float(st.get("cash", 0))
        positions = dict(st.get("positions", {}))
        prices = dict(S.get("prices", {}))
    for sym, pos in positions.items():
        total += to_float(pos.get("qty", 0)) * prices.get(sym, to_float(pos.get("avg", 0)))
    return int(total)


def _multi_ai_update(ai_id):
    asset = _multi_ai_asset(ai_id)
    with LOCK:
        st = S["paper_ais"][ai_id]
        st["asset"] = asset
        st["profit_rate"] = pct(asset, st.get("start_cash", MULTI_AI_START_CASH))
        peak = max(to_float(st.get("peak_asset", MULTI_AI_START_CASH)), asset)
        st["peak_asset"] = peak
        st["mdd_pct"] = min(to_float(st.get("mdd_pct", 0)), pct(asset, peak) if peak else 0)


def _multi_ai_record(ai_id, action, sym, price, qty, fee, pl, reason, partial=False):
    _multi_ai_update(ai_id)
    with LOCK:
        st = S["paper_ais"][ai_id]
        row = {
            "time": now_text(), "ai_id": ai_id, "ai_name": st.get("name", ai_id),
            "action": action, "symbol": sym, "name": name_of(sym),
            "price": round(to_float(price), 4), "qty": int(qty), "fee": int(fee),
            "pl": int(pl), "cash": int(to_float(st.get("cash", 0))),
            "asset": int(to_float(st.get("asset", 0))),
            "profit_rate": round(to_float(st.get("profit_rate", 0)), 4),
            "reason": reason, "partial": bool(partial), "real_order": False,
        }
        st.setdefault("trades", []).insert(0, row)
        st["trades"] = st["trades"][:200]
        st["last_action"] = f"{now_short()} {action} {name_of(sym)}"
    write_row(multi_ai_path(ai_id), ["time","ai_id","ai_name","action","symbol","name","price","qty","fee","pl","cash","asset","profit_rate","reason","partial","real_order"], row)
    save_state()


def _multi_ai_buy(ai_id, sym, reason, ratio=None):
    if not ensure_live_orderbook(sym):
        return False
    gate_ok, gate_reason = market_safety_gate(sym)
    if not gate_ok:
        return False
    ensure_multi_ai_states()
    with LOCK:
        st = S["paper_ais"][ai_id]
        if st.get("positions"):
            return False
        cash = int(to_float(st.get("cash", 0)))
    use_ratio = MULTI_AI_MAX_POSITION_RATIO if ratio is None else min(MULTI_AI_MAX_POSITION_RATIO, max(0.05, ratio))
    budget = int(cash * use_ratio)
    fee_rate = MULTI_AI_FEE_SIDE_PCT / 100
    fill = simulated_orderbook_fill(sym, "BUY", max_cash=budget / (1 + fee_rate))
    if not fill.get("ok"):
        return False
    qty = int(fill.get("qty", 0)); price = to_float(fill.get("avg_price", 0)); gross = int(round(fill.get("gross", 0)))
    fee = int(round(gross * fee_rate)); total = gross + fee
    while qty > 0 and total > cash:
        qty -= 1; gross = int(round(qty * price)); fee = int(round(gross * fee_rate)); total = gross + fee
    if qty <= 0:
        return False
    with LOCK:
        st = S["paper_ais"][ai_id]
        st["cash"] = cash - total
        st["positions"][sym] = {
            "qty": qty, "avg": price, "entry_time": now_text(), "entry_date": today(),
            "entry_total_cost": total, "entry_fee": fee, "high_after_buy": price,
        }
    _multi_ai_record(ai_id, "가상매수", sym, price, qty, fee, 0, reason, bool(fill.get("partial")))
    return True


def _multi_ai_sell(ai_id, sym, reason):
    ensure_multi_ai_states()
    with LOCK:
        st = S["paper_ais"][ai_id]
        pos = st.get("positions", {}).get(sym)
        if not isinstance(pos, dict): return False
        qty = int(to_float(pos.get("qty", 0))); avg = to_float(pos.get("avg", 0)); total_cost = int(to_float(pos.get("entry_total_cost", qty * avg)))
    gate_ok, _ = market_safety_gate(sym)
    if not gate_ok: return False
    fill = simulated_orderbook_fill(sym, "SELL", qty=qty)
    if not fill.get("ok"): return False
    sold = int(fill.get("qty", 0)); price = to_float(fill.get("avg_price", 0)); gross = int(round(fill.get("gross", 0)))
    fee = int(round(gross * MULTI_AI_FEE_SIDE_PCT / 100)); net = gross - fee
    cost_part = int(round(total_cost * sold / max(1, qty))); pl = net - cost_part; remain = qty - sold
    with LOCK:
        st = S["paper_ais"][ai_id]
        st["cash"] = int(to_float(st.get("cash", 0))) + net
        st["realized_pl"] = int(to_float(st.get("realized_pl", 0))) + pl
        if remain <= 0:
            st["positions"].pop(sym, None)
        else:
            pos["qty"] = remain
            pos["entry_total_cost"] = max(0, total_cost - cost_part)
            st["positions"][sym] = pos
    _multi_ai_record(ai_id, "가상매도", sym, price, sold, fee, pl, reason, remain > 0)
    return True


def _multi_ai_recent_metrics(sym):
    with LOCK:
        hist = list(S.get("history", {}).get(sym, []) or [])
        signals = dict(S.get("signals", {}))
    sig = signals.get(sym, {}) if isinstance(signals.get(sym), dict) else {}
    score = to_float(sig.get("score", 0))
    def move(points):
        if len(hist) >= points + 1 and to_float(hist[-points-1]) > 0:
            return pct(to_float(hist[-1]), to_float(hist[-points-1]))
        return 0.0
    r3 = move(3)
    r10 = move(10)
    high = max([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [0])
    low = min([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [0])
    cur = to_float(hist[-1]) if hist else 0
    from_high = pct(cur, high) if high else 0
    from_low = pct(cur, low) if low else 0
    return score, r3, r10, from_high, from_low




def _multi_ai_parent_id(ai_id):
    return MULTI_AI_PARENT.get(ai_id, ai_id)


def _multi_ai_index(ai_id):
    parent = _multi_ai_parent_id(ai_id)
    digits = ''.join(ch for ch in parent if ch.isdigit())
    return int(digits) if digits else 1


def _multi_ai_family(ai_id):
    parent = _multi_ai_parent_id(ai_id)
    return parent[:1] if parent else ''


def _multi_ai_universe_lists(ai_id, mode):
    # 포함형은 삼성전자·SK하이닉스 본주/레버리지/인버스를 후보에 추가한다.
    # 제외형은 동일 전략을 시장·섹터 ETF에만 적용한다.
    etf_long = ["122630","233740","069500","229200","494310","488080","469150"]
    etf_inv = ["252670","251340"]
    samsung_hynix_long = ["0193T0","000660","0193W0","005930"]
    samsung_hynix_inv = ["0197X0","0193L0"]
    include_family = MULTI_AI_UNIVERSE.get(ai_id) == "INCLUDE_SAMSUNG_HYNIX"
    if mode == "DOWN":
        return etf_inv + (samsung_hynix_inv if include_family else [])
    return etf_long + (samsung_hynix_long if include_family else [])

def _multi_ai_candidate(ai_id, mode):
    """그룹별 후보 선택. G그룹은 전체시장 실시간 스캐너만 사용한다."""
    if ai_id.startswith("G"):
        return full_market_candidate(ai_id)

    with LOCK:
        prices = dict(S.get("prices", {}))
    universe = _multi_ai_universe_lists(ai_id, mode)
    market_ref = "252670" if mode=="DOWN" else "069500"
    _,_,market_r10,_,_ = _multi_ai_recent_metrics(market_ref)
    scored=[]
    idx = _multi_ai_index(ai_id)
    family = _multi_ai_family(ai_id)
    parent = _multi_ai_parent_id(ai_id)
    for sym in universe:
        if prices.get(sym,0)<=0:
            continue
        score,r3,r10,from_high,from_low = _multi_ai_recent_metrics(sym)
        rel = r10-market_r10
        if family=="R":
            # 연구 후 고정형: 15개의 서로 다른 고정 규칙
            methods = idx % 5
            if methods==1: metric=score*0.4+r10*8+rel*4
            elif methods==2: metric=score*0.3-r3*8+from_low*4
            elif methods==3: metric=score*0.25+r3*14+(10 if from_high>=-0.25 else -15)
            elif methods==4: metric=score*0.3+from_low*6+r3*8 if -3.5<=from_high<=-0.3 else -999
            else: metric=score*0.55+rel*5-abs(r3)*2
        else:
            # 순방향 학습형: 현재까지 누적된 본인 계좌성과와 최근 흐름을 사용
            st=S.get("paper_ais",{}).get(ai_id,{})
            own_penalty=max(0.0,-to_float(st.get("profit_rate",0)))*0.25
            look = [3,5,7,10][(idx-1)%4]
            momentum = r3 if look<=3 else r10
            if parent=="W13": momentum=-r3
            if parent=="W15" and mode in ["CHOPPY","NO_TRADE","RECOVERY"]: metric=-999
            else: metric=score*0.35+momentum*10+rel*5+from_low*2-own_penalty
        scored.append((metric,sym,score,r3,r10,from_high,from_low,rel))
    return max(scored,default=(0,"",0,0,0,0,0,0),key=lambda x:x[0])

def _multi_ai_entry_window(ai_id, hhmm):
    family = _multi_ai_family(ai_id)
    idx = _multi_ai_index(ai_id)
    if family == "G":
        return "09:10" <= hhmm < "14:40"
    if family == "R":
        fixed={5:"09:15",6:"10:00",7:"11:00",8:"12:30",9:"13:00",10:"13:30"}
        if idx in fixed:
            t=fixed[idx]
            return t <= hhmm <= f"{t[:3]}{min(59,int(t[3:])+3):02d}"
        if idx==15:
            return "14:45" <= hhmm <= "15:05"
    return "09:15" <= hhmm < "14:30"


def _multi_ai_exit_reason(ai_id, sym, pos, mode, hhmm):
    price=to_float(S.get("prices",{}).get(sym,0)); avg=to_float(pos.get("avg",0))
    if price<=0 or avg<=0:
        return ""
    high=max(to_float(pos.get("high_after_buy",avg)),price)
    with LOCK:
        if sym in S["paper_ais"][ai_id]["positions"]:
            S["paper_ais"][ai_id]["positions"][sym]["high_after_buy"]=high
    profit=pct(price,avg); draw=pct(price,high)
    parent = _multi_ai_parent_id(ai_id)
    family = _multi_ai_family(ai_id)
    if family == "G":
        stops={"G01":-1.4,"G02":-1.8,"G03":-1.3,"G04":-1.6,"G05":-1.2}
        trails={"G01":-0.9,"G02":-1.1,"G03":-0.7,"G04":-0.9,"G05":-0.8}
        if profit<=stops[parent]: return f"{ai_id} 실시간 손실제한 {profit:.2f}%"
        if profit>=0.7 and draw<=trails[parent]: return f"{ai_id} 실시간 수익보호 {draw:.2f}%"
        if hhmm>="15:10": return f"{ai_id} 당일 15:10 청산"
    elif parent=="R14":
        if profit>=0.8 and draw<=-1.0: return f"{ai_id} 추적청산 {draw:.2f}%"
    else:
        if profit<=-2.0: return f"{ai_id} 손실제한 {profit:.2f}%"
        if profit>=0.8 and draw<=-1.0: return f"{ai_id} 수익보호 {draw:.2f}%"
        if parent!="R15" and hhmm>="15:10": return f"{ai_id} 당일청산"
    return ""


def _combo_reset_daily(ai_id):
    with LOCK:
        st = S["paper_ais"][ai_id]
        if st.get("combo_date") != today():
            st["combo_date"] = today()
            st["combo_phase"] = 0
            st["combo_last_symbol"] = ""
            st["last_decision_ts"] = 0


def _combo_mode_for_phase(ai_id, phase, market_mode):
    if ai_id == "C01":
        return "DOWN" if phase == 0 else "UP"
    if ai_id == "C02":
        return "DOWN"
    if ai_id == "C03":
        return "DOWN" if phase == 0 else "UP"
    # C04/C05는 그 시점까지 확인된 시장 상태만 이용한다.
    return "DOWN" if market_mode == "DOWN" else "UP"


def _combo_times(ai_id):
    # (1차 진입, 1차 청산, 2차 진입, 최종 청산)
    if ai_id == "C03":
        return "09:15", "11:30", "11:31", "14:00"
    return "09:15", "12:00", "12:01", "15:00"


def _combo_pick_candidate(ai_id, direction):
    # 선택 시점까지 저장된 가격·점수만 사용한다. 이후 가격은 절대 사용하지 않는다.
    metric, sym, score, r3, r10, from_high, from_low, rel = _multi_ai_candidate(ai_id, direction)
    return metric, sym, score, r3, r10, from_high, from_low, rel


def _run_combo_account(ai_id, market_mode, hhmm, now_ts):
    _combo_reset_daily(ai_id)
    entry1, exit1, entry2, exit2 = _combo_times(ai_id)
    with LOCK:
        st = S["paper_ais"][ai_id]
        phase = int(to_float(st.get("combo_phase", 0)))
        positions = dict(st.get("positions", {}))
        last_ts = to_float(st.get("last_decision_ts", 0))

    # 1차 포지션 청산
    if phase == 1 and positions and hhmm >= exit1:
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f"{ai_id} 1차 구간 {exit1} 청산"):
                with LOCK:
                    st = S["paper_ais"][ai_id]
                    st["combo_phase"] = 2
                    st["last_decision_ts"] = now_ts
        return True

    # 2차 포지션 최종 청산
    if phase == 3 and positions and hhmm >= exit2:
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f"{ai_id} 2차 구간 {exit2} 청산"):
                with LOCK:
                    st = S["paper_ais"][ai_id]
                    st["combo_phase"] = 4
                    st["last_decision_ts"] = now_ts
        return True

    if positions:
        return True
    if now_ts - last_ts < MULTI_AI_DECISION_COOLDOWN_SEC:
        return True

    # 1차 진입
    if phase == 0 and entry1 <= hhmm < exit1:
        direction = _combo_mode_for_phase(ai_id, 0, market_mode)
        metric, sym, score, r3, r10, from_high, from_low, rel = _combo_pick_candidate(ai_id, direction)
        if sym and metric >= 35:
            reason = (f"{MULTI_AI_NAMES[ai_id]} 1차 direction={direction}, metric={metric:.1f}, "
                      f"score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, rel={rel:.2f}%, "
                      f"decision_data_end={now_text()}")
            if _multi_ai_buy(ai_id, sym, reason, 0.70):
                with LOCK:
                    st = S["paper_ais"][ai_id]
                    st["combo_phase"] = 1
                    st["combo_last_symbol"] = sym
                    st["last_decision_ts"] = now_ts
                return True
        with LOCK:
            st = S["paper_ais"][ai_id]
            st["last_decision_ts"] = now_ts
            st["last_action"] = f"{now_short()} 1차 관망 metric={metric:.1f}"
        return True

    # 2차 진입
    if phase == 2 and entry2 <= hhmm < exit2:
        direction = _combo_mode_for_phase(ai_id, 1, market_mode)
        metric, sym, score, r3, r10, from_high, from_low, rel = _combo_pick_candidate(ai_id, direction)
        if sym and metric >= 35:
            reason = (f"{MULTI_AI_NAMES[ai_id]} 2차 direction={direction}, metric={metric:.1f}, "
                      f"score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, rel={rel:.2f}%, "
                      f"decision_data_end={now_text()}")
            if _multi_ai_buy(ai_id, sym, reason, 0.70):
                with LOCK:
                    st = S["paper_ais"][ai_id]
                    st["combo_phase"] = 3
                    st["combo_last_symbol"] = sym
                    st["last_decision_ts"] = now_ts
                return True
        with LOCK:
            st = S["paper_ais"][ai_id]
            st["last_decision_ts"] = now_ts
            st["last_action"] = f"{now_short()} 2차 관망 metric={metric:.1f}"
        return True
    return True


def run_multi_paper_ais():
    """70개 가상계좌. 실제 주문 함수는 절대 호출하지 않는다."""
    ensure_multi_ai_states()
    for ai_id in MULTI_AI_IDS:
        _multi_ai_update(ai_id)
    if not ENABLE_MULTI_PAPER_AI or not paper_auto_time_open():
        return
    mode=target_market_regime()
    now_ts=time.time()
    hhmm=now_kst().strftime("%H:%M")
    # 3그룹이 켜져 있으면 전체시장 순환검색을 먼저 수행한다.
    if any(x.startswith("G") for x in MULTI_AI_IDS):
        scan_full_market_universe(False)

    for ai_id in MULTI_AI_IDS:
        if ai_id.startswith("C"):
            _run_combo_account(ai_id, mode, hhmm, now_ts)
            continue
        with LOCK:
            st=S["paper_ais"][ai_id]
            positions=dict(st.get("positions",{}))
            last_ts=to_float(st.get("last_decision_ts",0))
        if positions:
            for sym,pos in list(positions.items()):
                reason=_multi_ai_exit_reason(ai_id,sym,pos,mode,hhmm)
                if reason:
                    ensure_live_orderbook(sym)
                    _multi_ai_sell(ai_id,sym,reason)
            continue
        if now_ts-last_ts<MULTI_AI_DECISION_COOLDOWN_SEC:
            continue
        if not _multi_ai_entry_window(ai_id,hhmm):
            continue
        parent = _multi_ai_parent_id(ai_id)
        family = _multi_ai_family(ai_id)
        if parent=="W15" and mode in ["CHOPPY","NO_TRADE","RECOVERY"]:
            with LOCK:
                st["last_decision_ts"]=now_ts
                st["last_action"]=f"{now_short()} 현금관망 {mode}"
            continue
        metric,sym,score,r3,r10,from_high,from_low,rel=_multi_ai_candidate(ai_id,mode)
        threshold = 48 if family=="G" else (42 if family=="W" else 40)
        if not sym or metric<threshold:
            with LOCK:
                st["last_decision_ts"]=now_ts
                st["decision_data_end"]=now_text()
                st["last_action"]=f"{now_short()} 관망 mode={mode} metric={metric:.1f}"
            continue
        if family=="G" and not ensure_live_orderbook(sym):
            with LOCK:
                st["last_decision_ts"]=now_ts
                st["last_action"]=f"{now_short()} 호가미수신 관망 {sym}"
            continue
        ratios = {"G01":0.60,"G02":0.70,"G03":0.55,"G04":0.50,"G05":0.65,
                  "W15":0.30,"R12":0.35,"R13":0.40}
        ratio=ratios.get(parent,0.70)
        reason=(f"{MULTI_AI_NAMES[ai_id]} group={MULTI_AI_GROUP[ai_id]}, "
                f"universe={MULTI_AI_UNIVERSE[ai_id]}, parent={parent}, mode={mode}, "
                f"metric={metric:.1f}, score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, "
                f"high={from_high:.2f}%, low={from_low:.2f}%, rel={rel:.2f}%, "
                f"decision_data_end={now_text()}")
        if _multi_ai_buy(ai_id,sym,reason,ratio):
            with LOCK:
                st["last_decision_ts"]=now_ts
                st["last_decision_date"]=today()
                st["decision_data_end"]=now_text()

def simulated_orderbook_fill(sym, side, max_cash=0, qty=0):
    """현재 호가 잔량을 위에서부터 소진해 가상 평균체결가/부분체결을 계산한다."""
    ob = S.setdefault("market_data_capture", {}).get("latest_orderbook", {}).get(sym, {})
    levels = ob.get("asks" if side == "BUY" else "bids", []) if isinstance(ob, dict) else []
    if not isinstance(levels, list) or not levels:
        return {"ok": False, "reason": "ORDERBOOK_EMPTY", "qty": 0, "avg_price": 0, "gross": 0}
    remain_cash = float(max_cash)
    remain_qty = int(qty)
    filled = 0
    gross = 0.0
    for level in levels:
        if not isinstance(level, dict):
            continue
        px = to_float(level.get("price", 0))
        avail = int(to_float(level.get("volume", 0)))
        if px <= 0 or avail <= 0:
            continue
        if side == "BUY":
            can = min(avail, int(remain_cash // px))
        else:
            can = min(avail, remain_qty)
        if can <= 0:
            continue
        filled += can
        gross += can * px
        if side == "BUY":
            remain_cash -= can * px
        else:
            remain_qty -= can
        if (side == "BUY" and remain_cash < px) or (side == "SELL" and remain_qty <= 0):
            break
    return {
        "ok": filled > 0, "reason": "OK" if filled > 0 else "NO_LIQUIDITY",
        "qty": filled, "avg_price": gross / filled if filled else 0, "gross": gross,
        "partial": (side == "SELL" and filled < qty),
        "orderbook_timestamp": ob.get("timestamp", "") if isinstance(ob, dict) else "",
    }

def shadow_fixed_buy(sym, reason):
    """호가잔량 기반 가상매수. 실제 주문 함수는 절대 호출하지 않는다."""
    gate_ok, gate_reason = market_safety_gate(sym)
    if not gate_ok:
        _shadow_write_signal("BLOCK", sym, 0, False, gate_reason)
        return False
    with LOCK:
        st = S["shadow_fixed"]
        if st.get("position") or st.get("stopped_today"):
            return False
        cash = int(to_float(st.get("cash", 0)))
        fee_rate = SHADOW_FEE_SIDE_PCT / 100
    fill = simulated_orderbook_fill(sym, "BUY", max_cash=cash / (1 + fee_rate))
    if not fill.get("ok"):
        _shadow_write_signal("BLOCK", sym, 0, False, fill.get("reason", "NO_FILL"))
        return False
    qty = int(fill["qty"])
    price = to_float(fill["avg_price"])
    gross = int(round(fill["gross"]))
    fee = int(round(gross * fee_rate))
    total_cost = gross + fee
    while qty > 0 and total_cost > cash:
        qty -= 1
        gross = int(round(qty * price))
        fee = int(round(gross * fee_rate))
        total_cost = gross + fee
    if qty <= 0:
        return False
    with LOCK:
        st = S["shadow_fixed"]
        st["cash"] = cash - total_cost
        st["position"] = {
            "symbol": sym,
            "qty": qty,
            "entry_price": price,
            "entry_time": now_text(),
            "entry_gross": gross,
            "entry_fee": fee,
            "entry_total_cost": total_cost,
        }
    _shadow_record("가상매수", sym, price, qty, 0, reason, fee)
    if SHADOW_FIXED_NOTIFY and ENABLE_SHADOW_TRADE_ALERT:
        send_telegram(
            f"🟢 균형형 가상매수\n종목: {name_of(sym)} ({sym})\n"
            f"체결가: {fmt_won(price)} / 수량: {qty}주 / 매수비용: {fmt_won(fee)}\n"
            f"사유: {reason}\n실계좌 주문: 없음",
            [[telegram_button("📊 대시보드", APP_URL)]],
        )
    return True


def shadow_fixed_sell(reason, mark_stop=False):
    """현재 가상포지션 전량매도. 실제 주문 함수는 절대 호출하지 않는다."""
    with LOCK:
        st = S["shadow_fixed"]
        pos = st.get("position")
        if not isinstance(pos, dict):
            return False
        sym = str(pos.get("symbol", ""))
        qty = int(to_float(pos.get("qty", 0)))
        entry = to_float(pos.get("entry_price", 0))
        entry_total_cost = int(to_float(pos.get("entry_total_cost", qty * entry)))
        if qty <= 0:
            return False
    gate_ok, gate_reason = market_safety_gate(sym)
    if not gate_ok:
        _shadow_write_signal("BLOCK", sym, 0, False, gate_reason)
        return False
    fill = simulated_orderbook_fill(sym, "SELL", qty=qty)
    if not fill.get("ok"):
        _shadow_write_signal("BLOCK", sym, 0, False, fill.get("reason", "NO_FILL"))
        return False
    sold_qty = int(fill.get("qty", 0))
    price = to_float(fill.get("avg_price", 0))
    if sold_qty <= 0 or price <= 0:
        return False
    qty = sold_qty
    with LOCK:
        st = S["shadow_fixed"]
        pos = st.get("position")
        entry_total_cost = int(round(to_float(pos.get("entry_total_cost", 0)) * qty / max(1, int(to_float(pos.get("qty", qty))))))
        gross = int(round(qty * price))
        fee = int(round(gross * SHADOW_FEE_SIDE_PCT / 100))
        net_proceeds = gross - fee
        pl = int(net_proceeds - entry_total_cost)
        st["cash"] = int(to_float(st.get("cash", 0))) + net_proceeds
        st["realized_pl"] = int(to_float(st.get("realized_pl", 0))) + pl
        original_qty = int(to_float(pos.get("qty", 0)))
        remain_qty = max(0, original_qty - qty)
        if remain_qty > 0:
            remain_ratio = remain_qty / max(1, original_qty)
            pos["qty"] = remain_qty
            pos["entry_gross"] = int(round(to_float(pos.get("entry_gross", 0)) * remain_ratio))
            pos["entry_fee"] = int(round(to_float(pos.get("entry_fee", 0)) * remain_ratio))
            pos["entry_total_cost"] = int(round(to_float(pos.get("entry_total_cost", 0)) * remain_ratio))
            st["position"] = pos
            reason = reason + f" / 부분체결 {qty}주, 잔여 {remain_qty}주"
        else:
            st["position"] = None
        if mark_stop:
            st["stopped_today"] = True
    _shadow_record("가상손절" if mark_stop else "가상매도", sym, price, qty, pl, reason, fee)
    if SHADOW_FIXED_NOTIFY and ENABLE_SHADOW_TRADE_ALERT:
        rate = pct(price, entry) if entry else 0
        title = "⛔ 균형형 가상손절" if mark_stop else "🔴 균형형 가상매도"
        send_telegram(
            f"{title}\n종목: {name_of(sym)} ({sym})\n"
            f"매수가: {fmt_won(entry)} / 매도가: {fmt_won(price)}\n"
            f"가격수익률: {rate:+.2f}% / 순가상손익: {fmt_won(pl)} / 매도비용: {fmt_won(fee)}\n"
            f"사유: {reason}\n실계좌 주문: 없음",
            [[telegram_button("📊 대시보드", APP_URL)]],
        )
    return True


def _shadow_check_stop_loss():
    """장중 매 루프마다 -3% 손절을 정규청산보다 먼저 검사."""
    with LOCK:
        st = S.get("shadow_fixed", {})
        pos = st.get("position")
        already_stopped = bool(st.get("stopped_today", False))
    if already_stopped or not isinstance(pos, dict):
        return False
    sym = str(pos.get("symbol", ""))
    entry = to_float(pos.get("entry_price", 0))
    current = to_float(S.get("prices", {}).get(sym, 0))
    if entry <= 0 or current <= 0:
        return False
    rate = pct(current, entry)
    if rate <= -abs(SHADOW_STOP_LOSS_PCT):
        return shadow_fixed_sell(
            f"자동손절: 매수가 대비 {rate:.2f}% ≤ -{abs(SHADOW_STOP_LOSS_PCT):.2f}%",
            mark_stop=True,
        )
    return False


def write_shadow_fixed_summary():
    """당일 최종요약은 하루 한 번만 저장."""
    _shadow_update_asset()
    with LOCK:
        st = dict(S.get("shadow_fixed", {}))
        pos = st.get("position") or {}
    row = {
        "time": now_text(),
        "strategy": SHADOW_FIXED_STRATEGY_ID,
        "start_cash": int(to_float(st.get("start_cash", 0))),
        "cash": int(to_float(st.get("cash", 0))),
        "asset": int(to_float(st.get("asset", 0))),
        "profit_rate": round(to_float(st.get("profit_rate", 0)), 4),
        "realized_pl": int(to_float(st.get("realized_pl", 0))),
        "position_symbol": pos.get("symbol", ""),
        "position_qty": int(to_float(pos.get("qty", 0))),
        "position_entry": to_float(pos.get("entry_price", 0)),
        "inv_signal": bool(st.get("inv_signal", False)),
        "lev_signal": bool(st.get("lev_signal", False)),
        "stopped_today": bool(st.get("stopped_today", False)),
        "last_action": st.get("last_action", ""),
    }
    write_row(
        shadow_fixed_summary_path(),
        ["time", "strategy", "start_cash", "cash", "asset", "profit_rate", "realized_pl",
         "position_symbol", "position_qty", "position_entry", "inv_signal", "lev_signal",
         "stopped_today", "last_action"],
        row,
    )
    if ENABLE_SHADOW_DAILY_SUMMARY_ALERT:
        send_telegram(
            f"📊 균형형 가상매매 일일요약\n"
            f"날짜: {today()}\n총자산: {fmt_won(row['asset'])}\n"
            f"누적수익률: {row['profit_rate']:+.2f}%\n실현손익: {fmt_won(row['realized_pl'])}\n"
            f"오늘 손절: {'예' if row['stopped_today'] else '아니오'}\n"
            f"최종상태: {row['last_action']}\n실계좌 주문: 없음",
            [[telegram_button("📊 대시보드", APP_URL)]],
        )


def run_shadow_fixed_strategy():
    """균형형 고정규칙 실전가정 가상체결.

    오전 하이닉스 인버스(0197X0), 오후 KODEX 레버리지(122630).
    각 시점까지 수집된 가격만 사용하고 실제 주문 함수는 절대 호출하지 않는다.
    """
    if not SHADOW_FIXED_ENABLED or is_weekend_kst():
        return

    _shadow_roll_date()

    # 분 종가 체크포인트 수집
    _shadow_checkpoint(SHADOW_INV_BASE_TIME, SHADOW_INV_SYMBOL)
    _shadow_checkpoint(SHADOW_INV_SIGNAL_TIME, SHADOW_INV_SYMBOL)
    _shadow_checkpoint(SHADOW_LEV_BASE_TIME, SHADOW_LEV_SYMBOL)
    _shadow_checkpoint(SHADOW_LEV_SIGNAL_TIME, SHADOW_LEV_SYMBOL)

    # 손절은 신호 평가와 정규청산보다 항상 먼저 실행
    _shadow_check_stop_loss()

    hhmm = now_kst().strftime("%H:%M")

    # 09:46: 오전 하이닉스 인버스 신호 평가 및 체결
    if hhmm == SHADOW_INV_ENTRY_TIME:
        with LOCK:
            done = bool(S["shadow_fixed"].get("inv_evaluated", False))
            stopped = bool(S["shadow_fixed"].get("stopped_today", False))
        if not done:
            p0 = _shadow_get_checkpoint(SHADOW_INV_SYMBOL, SHADOW_INV_BASE_TIME)
            p1 = _shadow_get_checkpoint(SHADOW_INV_SYMBOL, SHADOW_INV_SIGNAL_TIME)
            move = pct(p1, p0) if p0 > 0 and p1 > 0 else 999.0
            passed = (
                not stopped
                and p0 > 0 and p1 > 0
                and SHADOW_INV_MOVE_MIN_PCT <= move <= SHADOW_INV_MOVE_MAX_PCT
            )
            reason = (
                f"09:15→09:45 {name_of(SHADOW_INV_SYMBOL)} {move:+.2f}% / "
                f"허용 {SHADOW_INV_MOVE_MIN_PCT:+.2f}~{SHADOW_INV_MOVE_MAX_PCT:+.2f}%"
            )
            with LOCK:
                S["shadow_fixed"]["inv_evaluated"] = True
                S["shadow_fixed"]["inv_signal"] = passed
            _shadow_write_signal("INVERSE_ENTRY", SHADOW_INV_SYMBOL, move, passed, reason)
            if passed:
                shadow_fixed_buy(SHADOW_INV_SYMBOL, reason)

    # 12:46: 오후 KODEX 레버리지 신호 평가. 통과 시 인버스 청산 후 전환
    if hhmm == SHADOW_LEV_ENTRY_TIME:
        with LOCK:
            done = bool(S["shadow_fixed"].get("lev_evaluated", False))
            stopped = bool(S["shadow_fixed"].get("stopped_today", False))
        if not done:
            p0 = _shadow_get_checkpoint(SHADOW_LEV_SYMBOL, SHADOW_LEV_BASE_TIME)
            p1 = _shadow_get_checkpoint(SHADOW_LEV_SYMBOL, SHADOW_LEV_SIGNAL_TIME)
            move = pct(p1, p0) if p0 > 0 and p1 > 0 else 999.0
            passed = (
                not stopped
                and p0 > 0 and p1 > 0
                and SHADOW_LEV_MOVE_MIN_PCT <= move <= SHADOW_LEV_MOVE_MAX_PCT
            )
            reason = (
                f"11:45→12:45 {name_of(SHADOW_LEV_SYMBOL)} {move:+.2f}% / "
                f"허용 {SHADOW_LEV_MOVE_MIN_PCT:+.2f}~{SHADOW_LEV_MOVE_MAX_PCT:+.2f}%"
            )
            with LOCK:
                S["shadow_fixed"]["lev_evaluated"] = True
                S["shadow_fixed"]["lev_signal"] = passed
                pos = S["shadow_fixed"].get("position")
            _shadow_write_signal("LEVERAGE_ENTRY", SHADOW_LEV_SYMBOL, move, passed, reason)
            if passed:
                if isinstance(pos, dict) and pos.get("symbol") == SHADOW_INV_SYMBOL:
                    shadow_fixed_sell("12:46 KODEX 레버리지 신호 확정: 인버스→레버리지 전환")
                with LOCK:
                    no_pos = not bool(S["shadow_fixed"].get("position"))
                    stopped = bool(S["shadow_fixed"].get("stopped_today", False))
                if no_pos and not stopped:
                    shadow_fixed_buy(SHADOW_LEV_SYMBOL, reason)

    # 14:00: 오후 전환이 없었던 인버스만 종료
    if hhmm == SHADOW_INV_EXIT_TIME:
        with LOCK:
            pos = S["shadow_fixed"].get("position")
        if isinstance(pos, dict) and pos.get("symbol") == SHADOW_INV_SYMBOL:
            shadow_fixed_sell("14:00 하이닉스 인버스 고정 종료")

    # 15:00: KODEX 레버리지 종료. 안전상 남은 포지션도 종료
    if hhmm == SHADOW_LEV_EXIT_TIME:
        with LOCK:
            pos = S["shadow_fixed"].get("position")
        if isinstance(pos, dict):
            shadow_fixed_sell("15:00 균형형 고정전략 전량 종료")

    _shadow_update_asset()

    # 최종요약은 15:00 이후 포지션이 없을 때 하루 한 번만 저장
    if hhmm >= SHADOW_LEV_EXIT_TIME:
        with LOCK:
            st = S["shadow_fixed"]
            can_save = (not st.get("position")) and (not st.get("summary_saved", False))
            if can_save:
                st["summary_saved"] = True
        if can_save:
            write_shadow_fixed_summary()
            save_state()


def reset_base_and_paper():
    refresh_account_all(force=True)
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
# 짧은 단타 기록 전용 엔진
# - 실계좌 알림은 보내지 않는다.
# - 나중에 분석용으로 "그때 샀다면/팔았다면" 후보만 CSV에 남긴다.
# ============================================================

def fast_scalp_candidate(sym):
    if sym not in FAST_SCALP_ALLOWED_SYMBOLS:
        return False, "매매후보 아님"
    price = S["prices"].get(sym, 0)
    if price <= 0:
        return False, "현재가 없음"
    sig = S["signals"].get(sym, {})
    score = to_int(sig.get("score", 0))
    if score < FAST_SCALP_SCORE_MIN:
        return False, f"score 부족 {score}"
    if "진입" not in str(sig.get("label", "")) and score < 90:
        return False, "진입 신호 부족"
    wm20 = to_float(S["wma"].get(sym, {}).get("wma20", 0))
    if wm20 > 0 and price < wm20:
        return False, "WMA20 아래"
    mode = target_market_regime()
    if mode == "DOWN" and not is_inverse_symbol(sym):
        return False, "DOWN에서 롱 제외"
    if mode in ["UP", "RECOVERY", "SEMI_LEADER_UP"] and is_inverse_symbol(sym):
        return False, "상승모드에서 인버스 제외"
    if mode in ["CHOPPY", "NO_TRADE"]:
        return False, f"{mode} 관망"
    return True, f"FAST_LOG_ONLY {mode} score={score}"

def write_fast_scalp_log_only():
    if not ENABLE_FAST_SCALP_LOG_ONLY:
        return
    # 알림 폭탄 방지: 같은 종목은 FAST_SCALP_LOG_COOLDOWN_SEC마다 1회 기록
    headers = ["time", "symbol", "name", "price", "score", "signal", "mode", "reason", "alert_sent"]
    mode = target_market_regime()
    with LOCK:
        symbols = list(FAST_SCALP_ALLOWED_SYMBOLS)
    for sym in symbols:
        ok, reason = fast_scalp_candidate(sym)
        if not ok:
            continue
        key = f"FAST_SCALP_LOG_{today()}_{sym}"
        with LOCK:
            last = S["last_alert"].get(key, 0)
            if time.time() - last < FAST_SCALP_LOG_COOLDOWN_SEC:
                continue
            S["last_alert"][key] = time.time()
        sig = S["signals"].get(sym, {})
        write_row(fast_scalp_path(), headers, {
            "time": now_text(),
            "symbol": sym,
            "name": name_of(sym),
            "price": S["prices"].get(sym, 0),
            "score": sig.get("score", 0),
            "signal": sig.get("label", ""),
            "mode": mode,
            "reason": reason,
            "alert_sent": False,
        })


# ============================================================
# 토스 공식 시장데이터 수집
# ============================================================

def _hhmm_in_range(cur_hhmm, start_hhmm, end_hhmm):
    return start_hhmm <= cur_hhmm <= end_hhmm

def market_data_focus_time():
    # 호가 기반 가상체결은 장중 언제든 청산될 수 있으므로 정규장 전체에서 수집한다.
    # 4개 핵심 종목을 30초 간격으로 조회해 호출량을 제한한다.
    ok, _ = regular_market_open_now()
    return ok

def _result_dict(data):
    if not isinstance(data, dict):
        return {}
    result = data.get("result", data)
    return result if isinstance(result, dict) else {}

def capture_candles_1m():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    state = S.setdefault("market_data_capture", {})
    headers = ["saved_at", "symbol", "timestamp", "open", "high", "low", "close", "volume", "currency"]
    for sym in MARKET_DATA_CORE_SYMBOLS:
        code, data = api_get("/api/v1/candles", params={
            "symbol": sym,
            "interval": "1m",
            "count": max(1, min(10, MARKET_DATA_CANDLE_COUNT)),
            "adjusted": "true",
        }, timeout=10)
        if code != 200:
            continue
        result = _result_dict(data)
        candles = result.get("candles", []) if isinstance(result, dict) else []
        if not isinstance(candles, list):
            continue
        # API는 최신순일 수 있으므로 오래된 봉부터 저장한다.
        for c in reversed(candles):
            if not isinstance(c, dict):
                continue
            ts = str(c.get("timestamp", ""))
            if not ts:
                continue
            key = f"{sym}:{ts}"
            if state.setdefault("last_candle_minute", {}).get(sym) == key:
                continue
            write_row(candle_1m_path(sym), headers, {
                "saved_at": now_text(), "symbol": sym, "timestamp": ts,
                "open": c.get("openPrice", 0), "high": c.get("highPrice", 0),
                "low": c.get("lowPrice", 0), "close": c.get("closePrice", 0),
                "volume": c.get("volume", 0), "currency": c.get("currency", "KRW"),
            })
            state["last_candle_minute"][sym] = key
    # KOSPI/KOSDAQ 정식 1분봉도 함께 저장한다.
    for sym in ["KOSPI", "KOSDAQ"]:
        code, data = api_get(f"/api/v1/market-indicators/{sym}/candles", params={
            "interval": "1m", "count": max(1, min(10, MARKET_DATA_CANDLE_COUNT))
        }, timeout=10)
        if code != 200:
            continue
        result = _result_dict(data)
        candles = result.get("candles", []) if isinstance(result, dict) else []
        for c in reversed(candles if isinstance(candles, list) else []):
            if not isinstance(c, dict):
                continue
            ts = str(c.get("timestamp", ""))
            if not ts:
                continue
            key = f"{sym}:{ts}"
            if state.setdefault("last_candle_minute", {}).get(sym) == key:
                continue
            write_row(candle_1m_path(sym), headers, {
                "saved_at": now_text(), "symbol": sym, "timestamp": ts,
                "open": c.get("openPrice", 0), "high": c.get("highPrice", 0),
                "low": c.get("lowPrice", 0), "close": c.get("closePrice", 0),
                "volume": c.get("volume", 0), "currency": "INDEX",
            })
            state["last_candle_minute"][sym] = key

def capture_orderbook_and_trades():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE or not market_data_focus_time():
        return
    state = S.setdefault("market_data_capture", {})
    ob_headers = [
        "saved_at", "symbol", "api_timestamp", "best_ask", "best_bid", "spread",
        "ask_total_volume", "bid_total_volume", "bid_ask_ratio", "asks_json", "bids_json"
    ]
    tr_headers = ["saved_at", "symbol", "timestamp", "price", "volume", "currency"]
    for sym in MARKET_DATA_ORDERFLOW_SYMBOLS:
        code, data = api_get("/api/v1/orderbook", params={"symbol": sym}, timeout=8)
        if code == 200:
            result = _result_dict(data)
            asks = result.get("asks", []) if isinstance(result.get("asks", []), list) else []
            bids = result.get("bids", []) if isinstance(result.get("bids", []), list) else []
            api_ts = str(result.get("timestamp", ""))
            if api_ts and state.setdefault("last_orderbook_timestamp", {}).get(sym) != api_ts:
                ask_total = sum(to_float(x.get("volume", 0)) for x in asks if isinstance(x, dict))
                bid_total = sum(to_float(x.get("volume", 0)) for x in bids if isinstance(x, dict))
                best_ask = to_float(asks[0].get("price", 0)) if asks else 0
                best_bid = to_float(bids[0].get("price", 0)) if bids else 0
                state.setdefault("latest_orderbook", {})[sym] = {
                    "timestamp": api_ts, "best_ask": best_ask, "best_bid": best_bid,
                    "asks": asks, "bids": bids,
                }
                write_row(orderbook_path(sym), ob_headers, {
                    "saved_at": now_text(), "symbol": sym, "api_timestamp": api_ts,
                    "best_ask": best_ask, "best_bid": best_bid,
                    "spread": best_ask - best_bid if best_ask and best_bid else 0,
                    "ask_total_volume": int(ask_total), "bid_total_volume": int(bid_total),
                    "bid_ask_ratio": round(bid_total / ask_total, 4) if ask_total else 0,
                    "asks_json": json.dumps(asks, ensure_ascii=False, separators=(",", ":")),
                    "bids_json": json.dumps(bids, ensure_ascii=False, separators=(",", ":")),
                })
                state["last_orderbook_timestamp"][sym] = api_ts

        code, data = api_get("/api/v1/trades", params={
            "symbol": sym, "count": max(1, min(50, MARKET_DATA_TRADE_COUNT))
        }, timeout=8)
        if code != 200:
            continue
        result = data.get("result", []) if isinstance(data, dict) else []
        if not isinstance(result, list):
            continue
        last_seen = state.setdefault("last_trade_timestamp", {}).get(sym, "")
        new_rows = []
        for t in reversed(result):
            if not isinstance(t, dict):
                continue
            ts = str(t.get("timestamp", ""))
            if not ts or (last_seen and ts <= last_seen):
                continue
            new_rows.append(t)
        for t in new_rows:
            write_row(trades_path(sym), tr_headers, {
                "saved_at": now_text(), "symbol": sym, "timestamp": t.get("timestamp", ""),
                "price": t.get("price", 0), "volume": t.get("volume", 0),
                "currency": t.get("currency", "KRW"),
            })
        if new_rows:
            last_trade = new_rows[-1]
            state["last_trade_timestamp"][sym] = str(last_trade.get("timestamp", ""))
            state.setdefault("latest_trade", {})[sym] = {
                "timestamp": str(last_trade.get("timestamp", "")),
                "price": to_float(last_trade.get("price", 0)),
                "volume": to_float(last_trade.get("volume", 0)),
            }

def capture_market_investor_data():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    price_headers = ["saved_at", "symbol", "timestamp", "last_price"]
    code, data = api_get("/api/v1/market-indicators/prices", params={"symbols": "KOSPI,KOSDAQ"}, timeout=8)
    if code == 200:
        result = data.get("result", []) if isinstance(data, dict) else []
        for item in result if isinstance(result, list) else []:
            if not isinstance(item, dict):
                continue
            write_row(market_indicator_path(), price_headers, {
                "saved_at": now_text(), "symbol": item.get("symbol", ""),
                "timestamp": item.get("timestamp", ""), "last_price": item.get("lastPrice", 0),
            })

    headers = [
        "saved_at", "market", "date", "updated_at",
        "individual_buy", "individual_sell", "individual_net",
        "foreigner_buy", "foreigner_sell", "foreigner_net",
        "institution_buy", "institution_sell", "institution_net",
        "other_corp_buy", "other_corp_sell", "other_corp_net",
        "institution_breakdown_json"
    ]
    for market in ["KOSPI", "KOSDAQ"]:
        code, data = api_get(f"/api/v1/market-indicators/{market}/investor-trading", params={
            "interval": "1d", "count": 1
        }, timeout=10)
        if code != 200:
            continue
        result = _result_dict(data)
        records = result.get("records", []) if isinstance(result, dict) else []
        if not records or not isinstance(records[0], dict):
            continue
        r = records[0]
        def amounts(key):
            obj = r.get(key, {}) if isinstance(r.get(key, {}), dict) else {}
            buy = to_int(obj.get("buyAmount", 0))
            sell = to_int(obj.get("sellAmount", 0))
            return buy, sell, buy - sell
        ib, isell, inet = amounts("individual")
        fb, fs, fnet = amounts("foreigner")
        nb, ns, nnet = amounts("institution")
        ob, osell, onet = amounts("otherCorporation")
        inst = r.get("institution", {}) if isinstance(r.get("institution", {}), dict) else {}
        write_row(investor_trading_path(), headers, {
            "saved_at": now_text(), "market": market, "date": r.get("date", ""),
            "updated_at": r.get("updatedAt", ""),
            "individual_buy": ib, "individual_sell": isell, "individual_net": inet,
            "foreigner_buy": fb, "foreigner_sell": fs, "foreigner_net": fnet,
            "institution_buy": nb, "institution_sell": ns, "institution_net": nnet,
            "other_corp_buy": ob, "other_corp_sell": osell, "other_corp_net": onet,
            "institution_breakdown_json": json.dumps(inst.get("breakdown", {}), ensure_ascii=False, separators=(",", ":")),
        })

def maybe_capture_toss_market_data():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    state = S.setdefault("market_data_capture", {})
    now_ts = time.time()
    try:
        if now_ts - to_float(state.get("last_candle_ts", 0)) >= MARKET_DATA_CANDLE_SEC:
            capture_candles_1m()
            state["last_candle_ts"] = now_ts
        if now_ts - to_float(state.get("last_orderflow_ts", 0)) >= MARKET_DATA_ORDERFLOW_SEC:
            capture_orderbook_and_trades()
            state["last_orderflow_ts"] = now_ts
        if now_ts - to_float(state.get("last_investor_ts", 0)) >= MARKET_DATA_INVESTOR_SEC:
            capture_market_investor_data()
            state["last_investor_ts"] = now_ts
        state["status"] = "정상"
    except Exception as e:
        state["errors"] = to_int(state.get("errors", 0)) + 1
        state["status"] = f"오류: {e}"
        set_error(f"토스 시장데이터 수집 오류: {e}")

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
        # 계좌조회 실패로 cash/total_value가 0이면 정상 포트폴리오로 저장하지 않는다.
        if cash == 0 and total_value == 0:
            write_alert_log("BLOCK", "portfolio", "", 0, 0, "skip", "비정상 0원 계좌스냅샷 저장 차단", False, "")
            return
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
    if not ENABLE_DAILY_BACKUP_ALERT:
        return
    n = now_kst()
    if is_weekend_kst() or not (n.hour == 15 and 35 <= n.minute <= 37):
        return
    key = f"BACKUP_SENT_{today()}"
    with LOCK:
        if S["last_alert"].get(key):
            return
        S["last_alert"][key] = time.time()
    path = create_backup_zip()
    url = f"{APP_URL}/download_backup" if APP_URL else "/download_backup"
    caption = f"📦 오늘 데이터 백업 완료\n날짜: {today()}\n시간: {now_short()}\n다운로드 링크: {url}"
    ok, msg = send_telegram_file(path, caption, force=True)
    if not ok:
        send_telegram(caption + f"\n파일전송 실패: {msg}", [[telegram_button("백업 다운로드", url)]], force=True)

def loop():
    load_state()
    ensure_multi_ai_states()
    save_state()
    counter = 0
    last_news = 0
    initialized = False
    while True:
        try:
            # 토요일·일요일에는 데이터 수집, 계좌조회, 신호계산, 가상/실거래, 알림을 전부 중지한다.
            # 서버와 대시보드는 살아 있고 월요일이 되면 자동으로 다시 정상 운영한다.
            if is_weekend_kst():
                set_status_once("WEEKEND_PAUSE", "주말 휴무: 매매·알림·데이터수집 중지", 1800)
                time.sleep(max(60, REFRESH_SEC))
                continue

            if not initialized:
                get_token()
                refresh_kr_market_calendar(force=True)
                refresh_account_all()
                load_prices()
                calc_wma_all()
                analyze_news_keywords()
                calc_scores()
                initialized = True

            # 1) 가격과 계좌를 같은 루프에서 30초마다 갱신
            refresh_kr_market_calendar(force=False)
            load_prices()
            try:
                maybe_capture_toss_market_data()
            except Exception as e:
                set_error(f"시장데이터 수집 루프 오류: {e}")
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
            try:
                write_fast_scalp_log_only()
            except Exception as e:
                set_error(f"짧은단타 기록 오류: {e}")
            update_paper_asset()

            # 2-1) V4.10 목표 패턴 실계좌 알림 엔진
            try:
                run_real_pattern_alert_engine()
            except Exception as e:
                set_error(f"목표패턴 엔진 오류: {e}")

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
                gate_ok, gate_reason = market_safety_gate()
                if gate_ok:
                    run_paper_ai_if_enabled()
                else:
                    set_status_once(f"PAPER_GATE_{gate_reason}", f"가상매매 차단: {gate_reason}", 300)
            except Exception as e:
                set_error(f"가상매매 오류: {e}")

            try:
                gate_ok, gate_reason = market_safety_gate()
                if gate_ok:
                    run_multi_paper_ais()
                else:
                    set_status_once(f"MULTI_AI_GATE_{gate_reason}", f"A~F 가상AI 차단: {gate_reason}", 300)
            except Exception as e:
                set_error(f"A~F 가상AI 오류: {e}")

            try:
                gate_ok, gate_reason = market_safety_gate()
                if gate_ok:
                    run_shadow_fixed_strategy()
                else:
                    set_status_once(f"SHADOW_GATE_{gate_reason}", f"고정전략 차단: {gate_reason}", 300)
            except Exception as e:
                set_error(f"고정전략 가상체결 오류: {e}")

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
        if path == "/ipcheck":
            try:
                r = requests.get("https://api.ipify.org?format=json", timeout=8)
                body = r.text
            except Exception as e:
                body = json.dumps({"error": str(e)}, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return

        if path in ["/selfcheck", "/configcheck"]:
            return self.json_response({
                "ok": True,
                "version": OPERATING_VERSION,
                "paper_only_mode": PAPER_ONLY_MODE,
                "market_safety_gate_enabled": ENABLE_MARKET_SAFETY_GATE,
                "market_gate_ok": S.get("market_data_capture", {}).get("gate_ok", False),
                "market_gate_reason": S.get("market_data_capture", {}).get("gate_reason", ""),
                "kr_market_calendar": S.get("market_data_capture", {}).get("calendar", {}),
                "max_price_age_sec": MAX_PRICE_AGE_SEC,
                "max_orderbook_age_sec": MAX_ORDERBOOK_AGE_SEC,
                "protected_real_symbols": sorted(REAL_ORDER_BLOCKED_SYMBOLS),
                "orderbook_fill_simulation": True,
                "symbols": len(ALL),
                "real_auto_buy": ENABLE_REAL_AUTO_BUY,
                "real_auto_sell": ENABLE_REAL_AUTO_SELL,
                "auto_sell_profit_only": AUTO_SELL_PROFIT_ONLY,
                "auto_sell_loss_cut": AUTO_SELL_LOSS_CUT,
                "samsung_leverage_profit_only": True,
                "samsung_leverage_symbol": "0193W0",
                "samsung_leverage_loss_auto_sell": False,
                "real_order_enabled": ENABLE_REAL_ORDER,
                "app_url": APP_URL,
                "telegram_configured": telegram_enabled(),
                "log_root": LOG_ROOT,
                "sellable_endpoint": "/api/v1/sellable-quantity",
                "real_holding_management": True,
                "paper_auto_ai_2000": ENABLE_PAPER_AUTO,
                "multi_paper_ai_enabled": ENABLE_MULTI_PAPER_AI,
                "multi_paper_ai_ids": MULTI_AI_IDS,
                "multi_paper_ai_start_cash_each": MULTI_AI_START_CASH,
                "multi_paper_ai_total_virtual_cash": MULTI_AI_START_CASH * len(MULTI_AI_IDS),
            "full_market_universe_count": len(S.get("full_market", {}).get("universe", {})),
            "full_market_scanner_ready": bool(S.get("full_market", {}).get("universe")) and ENABLE_FULL_MARKET_SCANNER,
            "full_market_status": S.get("full_market", {}).get("status", "대기"),
            "full_market_stock_master_source": S.get("full_market", {}).get("stock_master_source", "없음"),
            "full_market_ranking_last_at": S.get("full_market", {}).get("ranking_last_at", ""),
            "full_market_ranking_errors": S.get("full_market", {}).get("ranking_errors", []),
            "full_market_candidate_count": len(S.get("full_market", {}).get("ranked", [])),
                "fixed_strategy_account_ids": [x for x in MULTI_AI_IDS if not x.startswith("G")],
                "daily_market_ai_ids": [x for x in MULTI_AI_IDS if x.startswith("G")],
                "fixed_strategy_account_count": len([x for x in MULTI_AI_IDS if not x.startswith("G")]),
                "daily_market_ai_count": len([x for x in MULTI_AI_IDS if x.startswith("G")]),
                "research_include_ids": [x for x in MULTI_AI_IDS if x.startswith("RI")],
                "research_exclude_ids": [x for x in MULTI_AI_IDS if x.startswith("RE")],
                "walk_include_ids": [x for x in MULTI_AI_IDS if x.startswith("WI")],
                "walk_exclude_ids": [x for x in MULTI_AI_IDS if x.startswith("WE")],
                "multi_ai_universe_types": MULTI_AI_UNIVERSE,
                "multi_ai_parent_strategies": MULTI_AI_PARENT,
                "multi_paper_ai_states": {ai: {
                    "name": S.get("paper_ais", {}).get(ai, {}).get("name", MULTI_AI_NAMES.get(ai, ai)),
                    "group": MULTI_AI_GROUP.get(ai, ""),
                    "universe_type": MULTI_AI_UNIVERSE.get(ai, ""),
                    "parent_strategy": MULTI_AI_PARENT.get(ai, ai),
                    "cash": int(to_float(S.get("paper_ais", {}).get(ai, {}).get("cash", 0))),
                    "asset": int(to_float(S.get("paper_ais", {}).get(ai, {}).get("asset", 0))),
                    "profit_rate": round(to_float(S.get("paper_ais", {}).get(ai, {}).get("profit_rate", 0)), 4),
                    "positions": S.get("paper_ais", {}).get(ai, {}).get("positions", {}),
                    "last_action": S.get("paper_ais", {}).get(ai, {}).get("last_action", ""),
                } for ai in MULTI_AI_IDS},
                "paper_auto_hours": f"{PAPER_AUTO_START}~{PAPER_AUTO_END}",
                "paper_auto_time_open": paper_auto_time_open(),
                "account_refresh_hours": f"{ACCOUNT_REFRESH_START}~{ACCOUNT_REFRESH_END}",
                "account_api_time_open": account_api_time_open(),
                "operating_modes": ["SEMI_LEADER_UP", "UP", "DOWN", "RECOVERY", "CHOPPY", "NO_TRADE"],
                "real_account_mode": "semi_auto_button_only",
                "paper_account_mode": "auto_ai_when_ENABLE_PAPER_AUTO_true",
                "refresh_sec": REFRESH_SEC,
                "toss_market_data_capture": ENABLE_TOSS_MARKET_DATA_CAPTURE,
                "market_data_candle_sec": MARKET_DATA_CANDLE_SEC,
                "market_data_orderflow_sec": MARKET_DATA_ORDERFLOW_SEC,
                "market_data_investor_sec": MARKET_DATA_INVESTOR_SEC,
                "market_data_core_symbols": MARKET_DATA_CORE_SYMBOLS,
                "market_data_orderflow_symbols": MARKET_DATA_ORDERFLOW_SYMBOLS,
                "market_data_focus_windows": MARKET_DATA_FOCUS_WINDOWS,
                "market_data_capture_state": S.get("market_data_capture", {}),
                "market_data_files": {
                    "directory": market_data_dir(),
                    "investor": investor_trading_path(),
                    "indicators": market_indicator_path(),
                },
                "alert_symbols": ALERT_SYMBOLS,
                "backup_zip": backup_zip_path(),
                "legacy_daytrade_removed": LEGACY_DAYTRADE_REMOVED,
                "score_buy_disabled": SCORE_BUY_DISABLED,
                "target_pattern_enabled": TARGET_PATTERN_ENABLED,
                "target_pattern_mode": target_market_regime(),
                "target_pattern_lookback_points": TARGET_PATTERN_LOOKBACK_POINTS,
                "real_target_symbols": REAL_TARGET_SYMBOLS,
                "paper_alert_enabled": False,
                "real_pattern_alert_enabled": True,
                "telegram_trade_buttons": f"{TELEGRAM_BUTTON_TTL_SEC}sec_direct_button_with_live_condition_recheck",
                "telegram_notify_hours": f"{TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END}",
                "shadow_fixed_enabled": SHADOW_FIXED_ENABLED,
                "shadow_fixed_start_cash": SHADOW_FIXED_START_CASH,
                "shadow_fixed_notify": SHADOW_FIXED_NOTIFY,
                "final_minimal_alert_mode": FINAL_MINIMAL_ALERT_MODE,
                "method63_candidate_alert": ENABLE_METHOD63_CANDIDATE_ALERT,
                "real_pattern_candidate_alert": ENABLE_REAL_PATTERN_CANDIDATE_ALERT,
                "holding_warning_alert": ENABLE_HOLDING_WARNING_ALERT,
                "general_signal_alert": ENABLE_GENERAL_SIGNAL_ALERT,
                "shadow_trade_alert": ENABLE_SHADOW_TRADE_ALERT,
                "shadow_daily_summary_alert": ENABLE_SHADOW_DAILY_SUMMARY_ALERT,
                "real_order_result_alert": ENABLE_REAL_ORDER_RESULT_ALERT,
                "real_autosell_result_alert": ENABLE_REAL_AUTOSELL_RESULT_ALERT,
                "daily_backup_alert": ENABLE_DAILY_BACKUP_ALERT,
                "kakao_mirror": ENABLE_KAKAO_MIRROR,
                "shadow_fixed_strategy_id": SHADOW_FIXED_STRATEGY_ID,
                "shadow_inv_symbol": SHADOW_INV_SYMBOL,
                "shadow_lev_symbol": SHADOW_LEV_SYMBOL,
                "shadow_inv_band": [SHADOW_INV_MOVE_MIN_PCT, SHADOW_INV_MOVE_MAX_PCT],
                "shadow_lev_band": [SHADOW_LEV_MOVE_MIN_PCT, SHADOW_LEV_MOVE_MAX_PCT],
                "shadow_stop_loss_pct": SHADOW_STOP_LOSS_PCT,
                "shadow_fee_side_pct": SHADOW_FEE_SIDE_PCT,
                "shadow_fixed_state": {
                    "date": S.get("shadow_fixed", {}).get("date", ""),
                    "cash": int(to_float(S.get("shadow_fixed", {}).get("cash", 0))),
                    "asset": int(to_float(S.get("shadow_fixed", {}).get("asset", 0))),
                    "profit_rate": round(to_float(S.get("shadow_fixed", {}).get("profit_rate", 0)), 4),
                    "position": S.get("shadow_fixed", {}).get("position"),
                    "last_action": S.get("shadow_fixed", {}).get("last_action", ""),
                },
                "weekend_disabled": True,
                "is_weekend_now": is_weekend_kst(),
                "backup_time": "15:35",
                "backup_send_window": "15:35~15:37",
                "toss_client_id": "설정됨" if CLIENT_ID else "없음",
                "toss_client_secret": "설정됨" if CLIENT_SECRET else "없음",
                "telegram_bot_token": "설정됨" if TELEGRAM_BOT_TOKEN else "없음",
                "telegram_chat_id": "설정됨" if TELEGRAM_CHAT_ID else "없음",
                "kakao_token": "설정됨" if KAKAO_TOKEN else "없음",
                "hynix_trade_symbols": sorted(list(HYNIX_TRADE_SYMBOLS)),
                "real_alert_mode": REAL_ALERT_MODE,
                "fast_scalp_alert": ENABLE_FAST_SCALP_ALERT,
                "fast_scalp_log_only": ENABLE_FAST_SCALP_LOG_ONLY,
                "recovery_candidate_engine": RECOVERY_CANDIDATE_ENGINE,
                "position_set_reentry": POSITION_SET_REENTRY,
                "family_mode_engine": FAMILY_MODE_ENGINE,
                "peak_profit_trailing_auto_sell": PEAK_PROFIT_TRAILING_AUTO_SELL,
                "alert_only_actionable": ALERT_ONLY_ACTIONABLE,
                "vi_after_recheck": VI_AFTER_RECHECK,
                "method63_hynix_engine": METHOD63_HYNIX_ENGINE,
                "method63_hynix_only": METHOD63_HYNIX_ONLY,
                "method63_start_time": METHOD63_START_TIME,
                "method63_max_sets_per_day": METHOD63_MAX_SETS_PER_DAY,
                "method63_same_direction_reentry": METHOD63_SAME_DIRECTION_REENTRY,
                "method63_reverse_wait_sec": METHOD63_REVERSE_WAIT_SEC,
                "breakeven_guard_auto_sell": BREAKEVEN_GUARD_AUTO_SELL,
                "breakeven_guard_trigger_pct": BREAKEVEN_GUARD_TRIGGER_PCT,
                "breakeven_guard_exit_pct": BREAKEVEN_GUARD_EXIT_PCT,
                "auto_sell_profit_start_pct": AUTO_SELL_PROFIT_START_PCT,
                "auto_sell_trail_drop_pct": AUTO_SELL_TRAIL_DROP_PCT,
                "button_price_drift_pct": MAX_BUTTON_PRICE_DRIFT_PCT,
                "telegram_button_ttl_sec": TELEGRAM_BUTTON_TTL_SEC,
                "no_buy_before": NO_BUY_BEFORE,
            })
        if path == "/api":
            return self.json_response({k: S[k] for k in ["status", "updated", "cash", "total_value", "profit_loss", "profit_rate", "prices", "wma", "scores", "signals", "market_score", "news", "paper", "daytrade", "last_error"]})
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
            send_signal_kakao(LEV, "🟢 [매수-실행] 테스트"); return self.result_page("진입 알림 테스트", "카카오 버튼 알림 전송 요청 완료")
        if path == "/test_sell":
            send_signal_kakao(LEV, "🔴 [매도-실행] 테스트"); return self.result_page("매도 알림 테스트", "카카오 버튼 알림 전송 요청 완료")
        if path == "/daytrade_exec":
            result = execute_daytrade_from_url(qs)
            return self.result_page("단타 실행 결과", json.dumps(result, ensure_ascii=False, indent=2))
        if path == "/telegram_order":
            result = handle_telegram_order(qs)
            return self.result_page("텔레그램 버튼 주문 결과", json.dumps(result, ensure_ascii=False, indent=2))
        if path == "/confirm":
            return self.confirm_page(qs)
        if path == "/download_csv":
            return self.download_file(summary_path(), f"summary_{today()}.csv")
        if path == "/download_orders":
            return self.download_file(orders_path(), f"real_orders_{today()}.csv")
        if path == "/download_paper":
            return self.download_file(paper_path(), f"paper_trades_{today()}.csv")
        if path == "/download_shadow_trades":
            return self.download_file(shadow_fixed_path(), f"shadow_fixed_trades_{today()}.csv")
        if path == "/download_shadow_signals":
            return self.download_file(shadow_fixed_signal_path(), f"shadow_fixed_signals_{today()}.csv")
        if path == "/download_shadow_summary":
            return self.download_file(shadow_fixed_summary_path(), f"shadow_fixed_summary_{today()}.csv")
        if path == "/download_portfolio":
            return self.download_file(portfolio_path(), f"portfolio_{today()}.csv")
        if path == "/download_swing":
            return self.download_file(swing_path(), f"swing_decision_{today()}.csv")
        if path == "/download_alert_log":
            return self.download_file(alert_log_path(), f"alert_log_{today()}.csv")
        if path == "/download_fast_scalp":
            return self.download_file(fast_scalp_path(), f"fast_scalp_signals_{today()}.csv")
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
        if path == "/reset_daytrade":
            return self.json_response({"ok": False, "message": "구 구 단타 단타 리셋은 V4.10에서 제거되었습니다."})
        return self.json_response({"ok": False, "message": "unknown path"})

    def render_dashboard(self):
        html_doc = f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>80억 프로젝트 실전 반자동 관제센터</title><meta http-equiv="refresh" content="60">{CSS}</head><body>
<h1>80억 프로젝트 실전 반자동 관제센터</h1>
<div class="sub">버전 {safe(OPERATING_VERSION)} | 전략 {safe(SHADOW_FIXED_STRATEGY_ID)} | 업데이트 {safe(S['updated'])} | 상태 {safe(S['status'])} | 계좌 {safe(S['account_seq'])}</div>
<div class="grid"><div>{self.account_card()}{self.shadow_fixed_card()}{self.holdings_card()}</div><div>{self.market_card()}{self.signal_card(SHADOW_LEV_SYMBOL,'red')}{self.signal_card(SHADOW_INV_SYMBOL,'blue')}{self.basic_card(HYNIX)}{self.stock_table()}</div><div>{self.test_card()}{self.news_card()}{self.alert_card()}{self.order_card()}{self.shadow_trade_card()}</div></div>
<script>
async function postJson(path, body){{const res=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}})}});return await res.json();}}
async function order(symbol,side,qtyId){{const qty=document.getElementById(qtyId).value;const sideText=side==='BUY'?'매수':'매도';if(!qty||Number(qty)<=0){{alert('수량이 0입니다.');return;}}if(!confirm(symbol+' '+qty+'주 실계좌 '+sideText+' 주문 전송?'))return;const data=await postJson('/order',{{symbol:symbol,side:side,qty:qty}});alert(JSON.stringify(data));location.reload();}}
async function paperBuy(symbol){{const data=await postJson('/paper_buy',{{symbol:symbol,ratio:0.5}});alert(data.ok?'가상매수 완료':'가상매수 실패');location.reload();}}
async function paperSell(symbol){{const data=await postJson('/paper_sell',{{symbol:symbol}});alert(data.ok?'가상매도 완료':'가상매도 실패');location.reload();}}
async function resetBase(){{if(!confirm('현재 토스 총자산으로 실계좌 기준금과 구 AI 가상계좌를 리셋할까요? 고정전략 1천만원 계좌는 유지됩니다.'))return;const data=await postJson('/reset_base',{{}});alert(JSON.stringify(data));location.reload();}}
function setQty(id,qty){{document.getElementById(id).value=qty;}}
</script></body></html>"""
        self.html_response(html_doc)

    def account_card(self):
        real_rate = pct(S["total_value"], S["real_base_cash"]) if S["real_base_cash"] else 0
        return f"""<div class="card"><h2>실계좌</h2><div class="small">실제 기준금</div><div class="mid yellow">{fmt_won(S['real_base_cash'])}</div><br><div class="small">총자산</div><div class="big yellow">{fmt_won(S['total_value'])}</div><div class="small">기준금 대비 {real_rate:.2f}%</div><br><div class="small">매수가능금액</div><div class="mid">{fmt_won(S['cash'])}</div><br><div class="small">평가손익</div><div class="mid {color_class(S['profit_loss'])}">{fmt_won(S['profit_loss'])}</div><div class="{color_class(S['profit_rate'])}">{S['profit_rate']}%</div><br><div class="small">실주문 상태</div><div class="{'green' if ENABLE_REAL_ORDER else 'red'}">{'활성화' if ENABLE_REAL_ORDER else '비활성화'}</div><button class="gold" onclick="resetBase()">실계좌 기준금 리셋</button></div>"""


    def daytrade_card(self):
        return ""

    def shadow_fixed_card(self):
        _shadow_update_asset()
        with LOCK:
            st = dict(S.get("shadow_fixed", {}))
            pos = st.get("position") if isinstance(st.get("position"), dict) else None
            checkpoints = dict(st.get("checkpoints", {}))

        asset = to_float(st.get("asset", SHADOW_FIXED_START_CASH))
        start_cash = to_float(st.get("start_cash", SHADOW_FIXED_START_CASH))
        cash = to_float(st.get("cash", SHADOW_FIXED_START_CASH))
        profit_rate = to_float(st.get("profit_rate", 0))
        realized_pl = to_float(st.get("realized_pl", 0))
        stopped = bool(st.get("stopped_today", False))

        pos_html = "<span class='gray'>보유 없음</span>"
        stop_html = "-"
        if pos:
            sym = str(pos.get("symbol", ""))
            qty = int(to_float(pos.get("qty", 0)))
            entry = to_float(pos.get("entry_price", 0))
            cur = to_float(S.get("prices", {}).get(sym, 0))
            pos_pl = (cur - entry) * qty if cur and entry else 0
            pos_rate = pct(cur, entry) if cur and entry else 0
            stop_price = entry * (1.0 - SHADOW_STOP_LOSS_PCT / 100.0) if entry else 0
            stop_html = fmt_won(stop_price)
            pos_html = (
                f"<b>{safe(name_of(sym))}</b> <span class='small'>({safe(sym)})</span><br>"
                f"{qty:,}주 / 매수가 {fmt_won(entry)} / 현재가 {fmt_won(cur)}<br>"
                f"평가손익 <span class='{color_class(pos_pl)}'>{fmt_won(pos_pl)} ({pos_rate:+.2f}%)</span>"
            )

        inv_state = "통과" if st.get("inv_signal") else ("탈락" if st.get("inv_evaluated") else "대기")
        lev_state = "통과" if st.get("lev_signal") else ("탈락" if st.get("lev_evaluated") else "대기")
        inv_cls = "green" if inv_state == "통과" else ("red" if inv_state == "탈락" else "gray")
        lev_cls = "green" if lev_state == "통과" else ("red" if lev_state == "탈락" else "gray")

        return f"""<div class='card'>
        <h2>고정전략 가상계좌</h2>
        <div class='small'>실계좌 주문 없음 / 자동 가상운영 {'ON' if SHADOW_FIXED_ENABLED else 'OFF'}</div>
        <div class='big yellow'>{fmt_won(asset)}</div>
        <div class='{color_class(asset-start_cash)}'>누적 {profit_rate:+.2f}% / 실현손익 {fmt_won(realized_pl)}</div>
        <table>
        <tr><td>시작금</td><td>{fmt_won(start_cash)}</td></tr>
        <tr><td>현금</td><td>{fmt_won(cash)}</td></tr>
        <tr><td>오전 종목</td><td>{safe(name_of(SHADOW_INV_SYMBOL))} ({SHADOW_INV_SYMBOL})</td></tr>
        <tr><td>오전 밴드</td><td>{SHADOW_INV_MOVE_MIN_PCT:+.1f}% ~ {SHADOW_INV_MOVE_MAX_PCT:+.1f}%</td></tr>
        <tr><td>오전 신호</td><td class='{inv_cls}'>{inv_state}</td></tr>
        <tr><td>오후 종목</td><td>{safe(name_of(SHADOW_LEV_SYMBOL))} ({SHADOW_LEV_SYMBOL})</td></tr>
        <tr><td>오후 밴드</td><td>{SHADOW_LEV_MOVE_MIN_PCT:+.1f}% ~ {SHADOW_LEV_MOVE_MAX_PCT:+.1f}%</td></tr>
        <tr><td>오후 신호</td><td class='{lev_cls}'>{lev_state}</td></tr>
        <tr><td>자동손절</td><td>-{SHADOW_STOP_LOSS_PCT:.1f}% / 현재 손절가 {stop_html}</td></tr>
        <tr><td>당일 손절</td><td class='{'red' if stopped else 'green'}'>{'발생·재진입 금지' if stopped else '없음'}</td></tr>
        </table>
        <div class='small'>현재 포지션</div><div>{pos_html}</div><br>
        <div class='small'>마지막 행동</div><div>{safe(st.get('last_action','없음'))}</div>
        </div>"""

    def shadow_trade_card(self):
        with LOCK:
            trades = list(S.get("shadow_fixed", {}).get("trades", []))
        rows = "".join(
            f"<tr><td class='small'>{safe(t.get('time',''))}</td>"
            f"<td>{safe(t.get('action',''))}</td>"
            f"<td>{safe(t.get('name', name_of(t.get('symbol',''))))} {int(to_float(t.get('qty',0)))}주</td>"
            f"<td class='{color_class(t.get('pl',0))}'>{fmt_won(t.get('pl',0))}</td>"
            f"<td class='small'>{safe(t.get('reason',''))}</td></tr>"
            for t in trades[:20]
        ) or "<tr><td colspan='5' class='gray'>아직 고정전략 거래 없음</td></tr>"
        return f"<div class='card'><h2>고정전략 가상매매 기록</h2><table><tr><th>시간</th><th>행동</th><th>종목</th><th>손익</th><th>사유</th></tr>{rows}</table></div>"

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
        return f"""<div class="card"><h2>AI 가상매매</h2><div class="small">가상 기준금 / 자동운영</div><div class="big yellow">{fmt_won(VIRTUAL_BASE_CASH)}</div><div class="small">ENABLE_PAPER_AUTO={'ON' if ENABLE_PAPER_AUTO else 'OFF'}</div><div class="small">가상 시작금</div><div class="mid yellow">{fmt_won(p.get('start_cash',0))}</div><br><div class="small">가상 총자산</div><div class="big {color_class(p.get('asset',0)-p.get('start_cash',0))}">{fmt_won(p.get('asset',0))}</div><div class="{color_class(p.get('profit_rate',0))}">{p.get('profit_rate',0):.2f}%</div><br><div class="small">실제 대비 차이</div><div class="mid {color_class(diff)}">{diff:.2f}%p</div><br><div class="small">가상 보유</div><div>{pos_rows}</div><br><div class="small">마지막 행동</div><div>{safe(p.get('last_action','없음'))}</div><br><button class="paperbtn" onclick="paperBuy('{LEV}')">가상 레버 매수</button><button class="paperbtn" onclick="paperBuy('{INV}')">가상 인버스 매수</button><button class="sell" onclick="paperSell('{LEV}')">가상 레버 매도</button><button class="sell" onclick="paperSell('{INV}')">가상 인버스 매도</button></div>"""

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
        return """<div class="card"><h2>테스트</h2><button class="graybtn" onclick="location.href='/refresh'">새로고침</button><button class="graybtn" onclick="location.href='/selfcheck'">SELF CHECK</button><button class="graybtn" onclick="location.href='/configcheck'">CONFIG CHECK</button><button class="graybtn" onclick="location.href='/check_kakao'">카카오 토큰</button><button class="graybtn" onclick="location.href='/test_kakao'">카카오/텔레 테스트</button><button class="graybtn" onclick="location.href='/check_telegram'">텔레그램 확인</button><button class="graybtn" onclick="location.href='/test_telegram'">텔레그램 테스트</button><button class="buy" onclick="location.href='/test_entry'">진입 알림 테스트</button><button class="sell" onclick="location.href='/test_sell'">매도 알림 테스트</button><button class="gold" onclick="location.href='/download_csv'">가격 CSV</button><button class="gold" onclick="location.href='/download_paper'">구 AI 가상매매 CSV</button><button class="gold" onclick="location.href='/download_shadow_signals'">고정규칙 신호 CSV</button><button class="gold" onclick="location.href='/download_shadow_trades'">고정규칙 거래 CSV</button><button class="gold" onclick="location.href='/download_shadow_summary'">고정규칙 요약 CSV</button><button class="gold" onclick="location.href='/download_orders'">주문 CSV</button><button class="gold" onclick="location.href='/download_portfolio'">포트폴리오 CSV</button><button class="gold" onclick="location.href='/download_swing'">스윙판단 CSV</button><button class="gold" onclick="location.href='/download_alert_log'">알림로그 CSV</button><button class="gold" onclick="location.href='/download_fast_scalp'">짧은단타 기록 CSV</button><button class="gold" onclick="location.href='/symbols_csv'">종목별 CSV</button><button class="gold" onclick="location.href='/download_backup'">오늘 전체 ZIP</button></div>"""

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

def print_operating_config():
    """Render 로그에 비밀값 원문 없이 현재 운영 설정을 한 번에 표시."""
    print("=" * 60, flush=True)
    print("[운영 설정 확인]", flush=True)
    print(f"version={OPERATING_VERSION}", flush=True)
    print(f"paper_only_mode={PAPER_ONLY_MODE}", flush=True)
    print(f"real_order={ENABLE_REAL_ORDER}", flush=True)
    print(f"real_auto_buy={ENABLE_REAL_AUTO_BUY}", flush=True)
    print(f"real_auto_sell={ENABLE_REAL_AUTO_SELL}", flush=True)
    print(f"paper_auto={ENABLE_PAPER_AUTO}", flush=True)
    print(f"shadow_fixed={SHADOW_FIXED_ENABLED}", flush=True)
    print(f"shadow_start_cash={SHADOW_FIXED_START_CASH:,}", flush=True)
    print(f"shadow_notify={SHADOW_FIXED_NOTIFY}", flush=True)
    print(f"telegram={TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END}", flush=True)
    print(f"account_refresh={ACCOUNT_REFRESH_START}~{ACCOUNT_REFRESH_END}", flush=True)
    print("backup=15:35~15:37", flush=True)
    print("weekend_disabled=True", flush=True)
    print(f"TOSS_CLIENT_ID={'SET' if CLIENT_ID else 'MISSING'}", flush=True)
    print(f"TOSS_CLIENT_SECRET={'SET' if CLIENT_SECRET else 'MISSING'}", flush=True)
    print(f"TELEGRAM_BOT_TOKEN={'SET' if TELEGRAM_BOT_TOKEN else 'MISSING'}", flush=True)
    print(f"TELEGRAM_CHAT_ID={'SET' if TELEGRAM_CHAT_ID else 'MISSING'}", flush=True)
    print(f"KAKAO_TOKEN={'SET' if KAKAO_TOKEN else 'MISSING'}", flush=True)
    print(f"configcheck={APP_URL}/configcheck", flush=True)
    print("=" * 60, flush=True)


def print_v431_selfcheck():
    universe = load_full_market_universe(True)
    print("[V4.32 SELFCHECK]", flush=True)
    print(" version=", OPERATING_VERSION, flush=True)
    print(" paper_only_mode=", PAPER_ONLY_MODE, flush=True)
    print(" real_order_enabled=", ENABLE_REAL_ORDER, flush=True)
    print(" paper_accounts=", len(MULTI_AI_IDS), flush=True)
    print(" groups=", {g:sum(1 for x in MULTI_AI_IDS if MULTI_AI_GROUP[x]==g) for g in set(MULTI_AI_GROUP.values())}, flush=True)
    print(" universes=", {u:sum(1 for x in MULTI_AI_IDS if MULTI_AI_UNIVERSE[x]==u) for u in set(MULTI_AI_UNIVERSE.values())}, flush=True)
    print(" full_market_universe_count=", len(universe), flush=True)
    print(" full_market_scanner_ready=", bool(universe) and ENABLE_FULL_MARKET_SCANNER, flush=True)
    print(" protected_real_symbols=", sorted(PROTECTED_REAL_SYMBOLS), flush=True)
    if not PAPER_ONLY_MODE or ENABLE_REAL_ORDER:
        raise RuntimeError("V4.32 안전차단 실패: PAPER_ONLY_MODE=true, ENABLE_REAL_ORDER=false 필요")
    if len(MULTI_AI_IDS) != 70:
        raise RuntimeError("V4.32 계좌 수 오류: 70개가 아님")
    if not universe:
        print(" WARNING: 토스 /api/v1/rankings에서 전체시장 후보를 받지 못해 G01~G05는 대기합니다.", flush=True)

if __name__ == "__main__":
    print_v431_selfcheck()
    print_operating_config()
    print("80억 프로젝트 실전 반자동 관제센터 시작:", PORT, flush=True)
    threading.Thread(target=loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
