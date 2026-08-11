# OPERATING_V4_80_DATA_PAPER_BACKUP_RAW_FIRST_FINAL_PAPER_ONLY
# 최종 동결형: KR/US 데이터 수집 + 90 가상계좌 + 검증 + 백업/Drive 전용.
# 실주문/실계좌/뉴스/매수후보 엔진 없음. 백업 실패가 수집 원본을 삭제하거나 중단시키지 않는다.
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urlencode
from datetime import datetime, timedelta
import os
import json
import csv
import html
import time
import uuid
import threading
import zipfile
import io
import tempfile
import shutil
try:
    import fcntl
except ImportError:
    fcntl = None
import xml.etree.ElementTree as ET
import hashlib
import random
import re
from collections import defaultdict
import requests
import pytz
OPERATING_VERSION = 'OPERATING_V4_82_DATA_PAPER_BACKUP_STORAGE_FALLBACK_FINAL_PAPER_ONLY'
DATA_PAPER_BACKUP_ONLY = True
RUNTIME_SCOPE = ('KR_DATA', 'US_DATA', 'PAPER_90', 'RAW_BACKUP', 'DRIVE_BACKUP', 'SELFCHECK')
KST = pytz.timezone('Asia/Seoul')
BASE = os.environ.get('TOSS_BASE', 'https://openapi.tossinvest.com').rstrip('/')
PORT = int(os.environ.get('PORT', '10000'))
APP_URL = os.environ.get('APP_URL', 'https://market-watch-6zgo.onrender.com').rstrip('/')
CLIENT_ID = os.environ.get('TOSS_CLIENT_ID', '').strip()
CLIENT_SECRET = os.environ.get('TOSS_CLIENT_SECRET', '').strip()
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
GOOGLE_DRIVE_CLIENT_ID = os.environ.get('GOOGLE_DRIVE_CLIENT_ID', '').strip()
GOOGLE_DRIVE_CLIENT_SECRET = os.environ.get('GOOGLE_DRIVE_CLIENT_SECRET', '').strip()
GOOGLE_DRIVE_REFRESH_TOKEN = os.environ.get('GOOGLE_DRIVE_REFRESH_TOKEN', '').strip()
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '').strip()
GOOGLE_DRIVE_REDIRECT_URI = os.environ.get('GOOGLE_DRIVE_REDIRECT_URI', 'https://market-watch-6zgo.onrender.com/google/oauth/callback').strip()
GOOGLE_DRIVE_UPLOAD_ENABLED = os.environ.get('GOOGLE_DRIVE_UPLOAD_ENABLED', 'true').lower() == 'true'
GOOGLE_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive'
GOOGLE_DRIVE_APPEND_ONLY = True
GOOGLE_DRIVE_ALLOW_DELETE = False
GOOGLE_DRIVE_ALLOW_UPDATE = False
GOOGLE_DRIVE_VERIFY_EXISTING_UNCHANGED = True
GOOGLE_DRIVE_CHUNK_BYTES = 8 * 1024 * 1024
GOOGLE_OAUTH_STATE = ''
GOOGLE_OAUTH_STATE_EXPIRES_AT = 0.0
PAPER_ONLY_MODE = True
ENABLE_REAL_ORDER = False
US_REAL_ORDER_ENABLED = False
ENABLE_PAPER_AUTO = os.environ.get('ENABLE_PAPER_AUTO', 'true').lower() == 'true'
REFRESH_SEC = int(os.environ.get('REFRESH_SEC', '30'))
MAX_BUY_RATIO = float(os.environ.get('MAX_BUY_RATIO', '0.70'))
VIRTUAL_BASE_CASH = int(float(os.environ.get('VIRTUAL_BASE_CASH', '10000000')))
ENABLE_MULTI_PAPER_AI = os.environ.get('ENABLE_MULTI_PAPER_AI', 'true').lower() == 'true'
MULTI_AI_START_CASH = int(float(os.environ.get('MULTI_AI_START_CASH', '10000000')))
MULTI_AI_FEE_SIDE_PCT = float(os.environ.get('MULTI_AI_FEE_SIDE_PCT', '0.10'))
MULTI_AI_MAX_POSITION_RATIO = float(os.environ.get('MULTI_AI_MAX_POSITION_RATIO', '0.90'))
MULTI_AI_DECISION_COOLDOWN_SEC = int(os.environ.get('MULTI_AI_DECISION_COOLDOWN_SEC', '180'))
RESEARCH_BASE_NAMES = {1: '연구고정 오전추세', 2: '연구고정 오전역추세', 3: '연구고정 오전돌파', 4: '연구고정 오전눌림', 5: '연구고정 09:15', 6: '연구고정 10:00', 7: '연구고정 11:00', 8: '연구고정 오후추세', 9: '연구고정 오후역추세', 10: '연구고정 오후돌파', 11: '연구고정 2구간', 12: '연구고정 저노출', 13: '연구고정 관망강화', 14: '연구고정 추적청산', 15: '연구고정 오버나이트'}
WALK_BASE_NAMES = {1: '순방향 누적수익 1위', 2: '순방향 누적 상위3 분산', 3: '순방향 최근3일 1위', 4: '순방향 최근5일 1위', 5: '순방향 최근7일 1위', 6: '순방향 최근10일 1위', 7: '순방향 최근5일 위험조정', 8: '순방향 최근10일 위험조정', 9: '순방향 최소MDD', 10: '순방향 승률우선', 11: '순방향 수익MDD 혼합', 12: '순방향 50·30·20', 13: '순방향 단기역추세', 14: '순방향 지연추세', 15: '순방향 현금관망'}
MULTI_AI_IDS = [f'RI{i:02d}' for i in range(1, 16)] + [f'RE{i:02d}' for i in range(1, 16)] + [f'WI{i:02d}' for i in range(1, 16)] + [f'WE{i:02d}' for i in range(1, 16)] + [f'G{i:02d}' for i in range(1, 6)] + [f'C{i:02d}' for i in range(1, 6)] + [f'L{i:02d}' for i in range(1, 6)] + [f'V{i:02d}' for i in range(1, 16)]
MULTI_AI_NAMES = {**{f'RI{i:02d}': f'1그룹 포함형 {RESEARCH_BASE_NAMES[i]}' for i in range(1, 16)}, **{f'RE{i:02d}': f'1그룹 제외형 {RESEARCH_BASE_NAMES[i]}' for i in range(1, 16)}, **{f'WI{i:02d}': f'2그룹 포함형 {WALK_BASE_NAMES[i]}' for i in range(1, 16)}, **{f'WE{i:02d}': f'2그룹 제외형 {WALK_BASE_NAMES[i]}' for i in range(1, 16)}, 'G01': '전체시장 거래대금·돈몰림', 'G02': '전체시장 추세·돌파', 'G03': '전체시장 눌림목·재상승', 'G04': '전체시장 급락·반전', 'G05': '전체시장 종합자율', 'C01': '조합 오전인버스→오후레버리지', 'C02': '조합 오전인버스→오후인버스', 'C03': '조합 11:30 방향전환', 'C04': '조합 삼성·하이닉스 포함 자율', 'C05': '조합 삼성·하이닉스 제외 자율', 'L01': '학습 직전5일 최근가중 1위', 'L02': '학습 직전5일 최근가중 상위3', 'L03': '학습 직전7일 수익 1위', 'L04': '학습 직전5일 수익·MDD 균형', 'L05': '학습 비용·낙폭 방어형', 'V01': '검증 4천만원 하루2회 494310·252670', 'V02': '검증 미래변수제거 하루2회', 'V03': '검증 1억원대 삼성·하이닉스 4종목', 'V04': '일봉 삼성·하이닉스·KODEX200 MA10 완전합의', 'V05': '일봉방향 + 장중 눌림 재진입', 'V06': '일봉방향 + 같은 방향 상대강도 1위', 'V07': '삼성전자·SK하이닉스 장중 방향합의', 'V08': '관망강화 데이터·혼조 필터', 'V09': '고정 09:15 진입 60분 보유', 'V10': '고정 10:00 진입 90분 보유', 'V11': '고정 11:00 진입 90분 보유', 'V12': '11시 방향합의 90분 보유', 'V13': '오버나이트 15:10 진입 다음날 09:05 청산', 'V14': '하루 최대4회 방향추종', 'V15': '장중 방향전환·재진입 2회'}
MULTI_AI_GROUP = {**{f'RI{i:02d}': 'RESEARCH_FIXED' for i in range(1, 16)}, **{f'RE{i:02d}': 'RESEARCH_FIXED' for i in range(1, 16)}, **{f'WI{i:02d}': 'WALK_FORWARD' for i in range(1, 16)}, **{f'WE{i:02d}': 'WALK_FORWARD' for i in range(1, 16)}, **{f'G{i:02d}': 'FULL_MARKET_LIVE' for i in range(1, 6)}, **{f'C{i:02d}': 'INTRADAY_COMBO' for i in range(1, 6)}, **{f'L{i:02d}': 'DAILY_LEARNING' for i in range(1, 6)}, **{f'V{i:02d}': 'EXPANDED_VERIFIED_RULE' for i in range(1, 16)}}
MULTI_AI_UNIVERSE = {**{f'RI{i:02d}': 'INCLUDE_SAMSUNG_HYNIX' for i in range(1, 16)}, **{f'RE{i:02d}': 'EXCLUDE_SAMSUNG_HYNIX' for i in range(1, 16)}, **{f'WI{i:02d}': 'INCLUDE_SAMSUNG_HYNIX' for i in range(1, 16)}, **{f'WE{i:02d}': 'EXCLUDE_SAMSUNG_HYNIX' for i in range(1, 16)}, **{f'G{i:02d}': 'FULL_MARKET' for i in range(1, 6)}, 'C01': 'INCLUDE_SAMSUNG_HYNIX', 'C02': 'INCLUDE_SAMSUNG_HYNIX', 'C03': 'INCLUDE_SAMSUNG_HYNIX', 'C04': 'INCLUDE_SAMSUNG_HYNIX', 'C05': 'EXCLUDE_SAMSUNG_HYNIX', **{f'L{i:02d}': 'FULL_MARKET' for i in range(1, 6)}, 'V01': 'VERIFIED_494310_252670', 'V02': 'VERIFIED_494310_252670', 'V03': 'VERIFIED_SAMSUNG_HYNIX_4', **{f'V{i:02d}': 'ALL26_PAPER' for i in range(4, 16)}}
MULTI_AI_PARENT = {**{f'RI{i:02d}': f'R{i:02d}' for i in range(1, 16)}, **{f'RE{i:02d}': f'R{i:02d}' for i in range(1, 16)}, **{f'WI{i:02d}': f'W{i:02d}' for i in range(1, 16)}, **{f'WE{i:02d}': f'W{i:02d}' for i in range(1, 16)}, **{f'G{i:02d}': f'G{i:02d}' for i in range(1, 6)}, **{f'C{i:02d}': f'C{i:02d}' for i in range(1, 6)}, **{f'L{i:02d}': f'L{i:02d}' for i in range(1, 6)}, **{f'V{i:02d}': f'V{i:02d}' for i in range(1, 16)}}
ENABLE_FULL_MARKET_SCANNER = os.environ.get('ENABLE_FULL_MARKET_SCANNER', 'true').lower() == 'true'
FULL_MARKET_SCAN_INTERVAL_SEC = int(os.environ.get('FULL_MARKET_SCAN_INTERVAL_SEC', '60'))
FULL_MARKET_TOP_N = int(os.environ.get('FULL_MARKET_TOP_N', '80'))
FULL_MARKET_RANKING_COUNT = int(os.environ.get('FULL_MARKET_RANKING_COUNT', '100'))
FULL_MARKET_RANKING_TYPES = ['MARKET_TRADING_AMOUNT', 'MARKET_TRADING_VOLUME', 'TOP_GAINERS', 'TOP_LOSERS']
FULL_MARKET_MIN_PRICE = int(os.environ.get('FULL_MARKET_MIN_PRICE', '1000'))
FULL_MARKET_MIN_TURNOVER = float(os.environ.get('FULL_MARKET_MIN_TURNOVER', '1000000000'))
FULL_MARKET_BLOCKED_SYMBOLS_BASE = {'000660', '005930', '0193L0', '0193T0', '0193W0', '0197X0'}
ENABLE_MARKET_SAFETY_GATE = os.environ.get('ENABLE_MARKET_SAFETY_GATE', 'true').lower() == 'true'
MARKET_CALENDAR_REFRESH_SEC = int(os.environ.get('MARKET_CALENDAR_REFRESH_SEC', '1800'))
MAX_PRICE_AGE_SEC = int(os.environ.get('MAX_PRICE_AGE_SEC', '90'))
MAX_ORDERBOOK_AGE_SEC = int(os.environ.get('MAX_ORDERBOOK_AGE_SEC', '90'))
REQUIRE_FRESH_ORDERBOOK_FOR_PAPER = os.environ.get('REQUIRE_FRESH_ORDERBOOK_FOR_PAPER', 'true').lower() == 'true'
PAPER_BLOCKED_SYMBOLS = {x.strip() for x in os.environ.get('PAPER_BLOCKED_SYMBOLS', '0193W0').split(',') if x.strip()}
FULL_MARKET_BLOCKED_SYMBOLS = FULL_MARKET_BLOCKED_SYMBOLS_BASE | PAPER_BLOCKED_SYMBOLS
ENABLE_TOSS_MARKET_DATA_CAPTURE = os.environ.get('ENABLE_TOSS_MARKET_DATA_CAPTURE', 'true').lower() == 'true'
MARKET_DATA_CANDLE_SEC = int(os.environ.get('MARKET_DATA_CANDLE_SEC', '60'))
MARKET_DATA_ORDERFLOW_SEC = int(os.environ.get('MARKET_DATA_ORDERFLOW_SEC', '30'))
MARKET_DATA_INVESTOR_SEC = int(os.environ.get('MARKET_DATA_INVESTOR_SEC', '300'))
MARKET_DATA_CANDLE_COUNT = int(os.environ.get('MARKET_DATA_CANDLE_COUNT', '3'))
MARKET_DATA_TRADE_COUNT = int(os.environ.get('MARKET_DATA_TRADE_COUNT', '20'))
# 데이터 보존 경로. 운영 기본은 영구스토리지 강제다.
# DATA_ROOT/LOG_ROOT가 지정되면 그 경로를 사용하고, 아니면 /var/data/market-watch를 우선 사용한다.
# /tmp는 테스트/비상용으로만 명시적으로 ALLOW_EPHEMERAL_STORAGE=true일 때 허용한다.
REQUIRE_PERSISTENT_STORAGE = os.environ.get('REQUIRE_PERSISTENT_STORAGE', 'true').lower() == 'true'
ALLOW_EPHEMERAL_STORAGE = os.environ.get('ALLOW_EPHEMERAL_STORAGE', 'false').lower() == 'true'
STRICT_PERSISTENT_STORAGE = os.environ.get('STRICT_PERSISTENT_STORAGE', 'false').lower() == 'true'
PERSISTENT_DISK_MOUNT_PATH = os.environ.get('PERSISTENT_DISK_MOUNT_PATH', '/var/data').rstrip('/') or '/var/data'

def _default_data_root():
    explicit = os.environ.get('DATA_ROOT', '').strip() or os.environ.get('LOG_ROOT', '').strip()
    if explicit:
        return explicit
    if os.path.isdir('/var/data') and os.access('/var/data', os.W_OK):
        return '/var/data/market-watch'
    return '/tmp/logs'

LOG_ROOT = _default_data_root()
BACKUP_ROOT = os.environ.get('BACKUP_ROOT', os.path.join(LOG_ROOT, '_backups')).strip()
STATE_PATH = os.environ.get('STATE_PATH', os.path.join(LOG_ROOT, '_state', 'state.json')).strip()
STATE_BAK_PATH = STATE_PATH + '.bak'
HEALTH_ROOT = os.path.join(LOG_ROOT, '_health')
INSTANCE_LOCK_PATH = os.path.join(LOG_ROOT, '_locks', 'collector.lock')
INSTANCE_LOCK_HANDLE = None

MAIN = {'0193T0': '하이닉스 레버리지', '0197X0': '하이닉스 인버스', '000660': 'SK하이닉스'}
MARKET = {'122630': 'KODEX 레버리지', '252670': 'KODEX 인버스2X', '069500': 'KODEX 200', '233740': '코스닥150 레버리지', '251340': '코스닥150 인버스', '229200': 'KODEX 코스닥150'}
WATCH = {'0193W0': '삼성전자 레버리지', '0193L0': '삼성전자 인버스', '005930': '삼성전자', '494310': '반도체 레버리지', '488080': 'TIGER 반도체TOP10', '469150': 'AI반도체', '0100K0': '방산 레버리지', '0080Y0': '조선 레버리지', '462330': '2차전지 레버리지', '0177X0': '로봇 휴머노이드', '445290': '로봇액티브', '433500': '원자력', '487240': 'AI전력인프라', '418660': '나스닥100 레버리지', '465610': '미국빅테크TOP7', '225040': 'S&P500 레버리지', '0127R0': 'AI클라우드'}
ALL = {**MAIN, **MARKET, **WATCH}
ALL26_SYMBOLS = list(ALL.keys())
MARKET_DATA_CORE_SYMBOLS = ALL26_SYMBOLS.copy()
MARKET_DATA_ORDERFLOW_SYMBOLS = ALL26_SYMBOLS.copy()
MARKET_DATA_DAILY_SYMBOLS = ALL26_SYMBOLS.copy()
MARKET_DATA_METADATA_SYMBOLS = ALL26_SYMBOLS.copy()
MARKET_DATA_DAILY_REFRESH_SEC = int(os.environ.get('MARKET_DATA_DAILY_REFRESH_SEC', '1800'))
MARKET_DATA_METADATA_REFRESH_SEC = int(os.environ.get('MARKET_DATA_METADATA_REFRESH_SEC', '21600'))
MARKET_DATA_AUDIT_SEC = int(os.environ.get('MARKET_DATA_AUDIT_SEC', '300'))
MARKET_DATA_DAILY_COUNT = max(1, min(200, int(os.environ.get('MARKET_DATA_DAILY_COUNT', '200'))))
MARKET_DATA_REQUEST_GAP_SEC = max(0.0, float(os.environ.get('MARKET_DATA_REQUEST_GAP_SEC', '0.12')))
ENABLE_US_MARKET_DATA_CAPTURE = os.environ.get('ENABLE_US_MARKET_DATA_CAPTURE', 'true').lower() == 'true'
US_SYMBOLS = [x.strip().upper() for x in os.environ.get('US_SYMBOLS', 'SPY,QQQ,TQQQ,SQQQ,UPRO,SPXU,SOXL,SOXS,NVDA,NVDL,NVD,TSLA,TSLL,TSLQ').split(',') if x.strip()]
US_CANDLE_SEC = max(60, int(os.environ.get('US_CANDLE_SEC', '60')))
US_ORDERFLOW_SEC = max(30, int(os.environ.get('US_ORDERFLOW_SEC', '60')))
US_METADATA_REFRESH_SEC = max(3600, int(os.environ.get('US_METADATA_REFRESH_SEC', '21600')))
US_BACKUP_DELAY_MIN = max(2, int(os.environ.get('US_BACKUP_DELAY_MIN', '5')))
TOSS_OPENAPI_SPEC_VERSION = '1.2.9'
TOSS_OPENAPI_SPEC_URL = 'https://openapi.tossinvest.com/openapi-docs/latest/openapi.json'
MARKET_MODE = 'KR_US_PAPER_ONLY'
KR_FIRST_CANDLE_REPAIR_START_MIN = max(2, int(os.environ.get('KR_FIRST_CANDLE_REPAIR_START_MIN', '2')))
KR_FIRST_CANDLE_REPAIR_END_MIN = max(KR_FIRST_CANDLE_REPAIR_START_MIN, int(os.environ.get('KR_FIRST_CANDLE_REPAIR_END_MIN', '15')))
KR_TARGETED_BACKFILL_RETRIES = max(1, min(8, int(os.environ.get('KR_TARGETED_BACKFILL_RETRIES', '5'))))
ENABLE_RAW_API_CAPTURE = os.environ.get('ENABLE_RAW_API_CAPTURE', 'true').lower() == 'true'
RAW_API_MAX_BODY_CHARS = int(os.environ.get('RAW_API_MAX_BODY_CHARS', '2000000'))
RATE_MIN_GAP_SEC = {'MARKET_DATA': max(0.1, float(os.environ.get('RATE_GAP_MARKET_DATA', '0.12'))), 'MARKET_DATA_CHART': max(0.2, float(os.environ.get('RATE_GAP_MARKET_DATA_CHART', '0.22'))), 'MARKET_INFO': max(0.34, float(os.environ.get('RATE_GAP_MARKET_INFO', '0.36'))), 'STOCK': max(0.2, float(os.environ.get('RATE_GAP_STOCK', '0.22'))), 'RANKING': max(0.2, float(os.environ.get('RATE_GAP_RANKING', '0.22'))), 'MARKET_INDICATOR_PRICE': max(0.1, float(os.environ.get('RATE_GAP_MARKET_INDICATOR_PRICE', '0.12'))), 'MARKET_INDICATOR': max(0.1, float(os.environ.get('RATE_GAP_MARKET_INDICATOR', '0.12'))), 'MARKET_INDICATOR_CHART': max(0.2, float(os.environ.get('RATE_GAP_MARKET_INDICATOR_CHART', '0.22'))), 'OTHER': max(0.2, float(os.environ.get('RATE_GAP_OTHER', '0.22')))}
RATE_GROUP_BY_PATH = {'/api/v1/prices': 'MARKET_DATA', '/api/v1/orderbook': 'MARKET_DATA', '/api/v1/trades': 'MARKET_DATA', '/api/v1/price-limits': 'MARKET_DATA', '/api/v1/candles': 'MARKET_DATA_CHART', '/api/v1/stocks': 'STOCK', '/api/v1/rankings': 'RANKING', '/api/v1/market-calendar/KR': 'MARKET_INFO', '/api/v1/market-calendar/US': 'MARKET_INFO', '/api/v1/exchange-rate': 'MARKET_INFO', '/api/v1/market-indicators/prices': 'MARKET_INDICATOR_PRICE'}

def _rate_group_for_path(path):
    """토스증권 공식 Rate Limits Group 기준으로 동적 경로까지 분류한다."""
    p = str(path or '')
    if p in RATE_GROUP_BY_PATH:
        return RATE_GROUP_BY_PATH[p]
    if p.startswith('/api/v1/stocks/'):
        return 'STOCK'
    if p.startswith('/api/v1/market-indicators/'):
        if p.endswith('/candles'):
            return 'MARKET_INDICATOR_CHART'
        if p.endswith('/investor-trading'):
            return 'MARKET_INDICATOR'
        return 'MARKET_INDICATOR'
    return 'OTHER'
API_CALL_LOCK = threading.RLock()
TOKEN_REFRESH_LOCK = threading.RLock()
INGEST_LOCK = threading.RLock()
INGEST_SEQ = 0
RATE_STATE = defaultdict(dict)
RATE_NEXT_ALLOWED = defaultdict(float)
CSV_KEY_CACHE = {}
CSV_KEY_LOCK = threading.RLock()
BACKUP_LOCK = threading.RLock()
LEV = '0193T0'
INV = '0197X0'
HYNIX = '000660'
ALERT_SYMBOLS = list(dict.fromkeys([
    LEV, '494310', '0193W0', '122630', '233740',
    INV, '0193L0', '252670', '251340',
    HYNIX, '005930', '069500', '229200'
]))
SEMI_LONG_SYMBOLS = [LEV, HYNIX, '494310', '488080', '469150', '122630', '069500', '0193W0', '005930']
UP_LONG_SYMBOLS = [LEV, HYNIX, '494310', '488080', '122630', '069500', '0193W0', '005930']
INVERSE_SYMBOLS = [INV, '252670', '0193L0', '251340']
SWING_BUY_STEP_AMOUNTS = [7000000, 4000000, 4000000]
SWING_MAX_EXPOSURE = 15000000
MIN_DEFENSE_CASH = 5000000
INVERSE_MAX_EXPOSURE = 15000000
NO_BUY_BEFORE = os.environ.get('NO_BUY_BEFORE', '09:15')
NO_NEW_BUY_AFTER = '14:30'
PAPER_DAYTRADE_FORCE_EXIT_TIME = '15:20'
PAPER_AUTO_START = os.environ.get('PAPER_AUTO_START', '09:00')
PAPER_AUTO_END = os.environ.get('PAPER_AUTO_END', '15:20')
PAPER_WAIT_LOG_COOLDOWN_SEC = int(os.environ.get('PAPER_WAIT_LOG_COOLDOWN_SEC', '600'))
TARGET_PATTERN_LOOKBACK_POINTS = int(os.environ.get('TARGET_PATTERN_LOOKBACK_POINTS', '600'))
TARGET_LONG_PULLBACK_PCT = float(os.environ.get('TARGET_LONG_PULLBACK_PCT', '8.0'))
TELEGRAM_NOTIFY_START = os.environ.get('TELEGRAM_NOTIFY_START', '08:50')
TELEGRAM_NOTIFY_END = os.environ.get('TELEGRAM_NOTIFY_END', '15:30')
ENABLE_DAILY_BACKUP_ALERT = True
ENABLE_REAL_AUTO_BUY = False
ENABLE_REAL_AUTO_SELL = False
LOCK = threading.RLock()
S = {'token': '', 'token_exp': 0, 'token_last_error': '', 'outbound_ip': '확인 전', 'outbound_ip_checked_at': 0, 'outbound_ip_error': '', 'status': '시작 중', 'updated': '없음', 'last_error': '', 'prices': {}, 'prev_prices': {}, 'history': {}, 'high': {}, 'low': {}, 'wma': {}, 'scores': {}, 'signals': {}, 'market_score': {'kospi': 0, 'kosdaq': 0, 'total': 0, 'label': '대기'}, 'alerts': [], 'last_alert': {}, 'us_backup_completed': {}, 'kr_backup_completed': {}, 'google_drive': {'status': 'DISABLED' if not GOOGLE_DRIVE_UPLOAD_ENABLED else 'WAITING_FOR_BACKUP', 'last_attempt_at': '', 'last_success_at': '', 'last_file_name': '', 'last_file_id': '', 'last_file_size': 0, 'last_web_view_link': '', 'last_error': '', 'retry_count': 0}, 'paper': {'start_cash': 0, 'cash': 0, 'positions': {}, 'trades': [], 'realized_pl': 0, 'asset': 0, 'profit_rate': 0, 'last_action': '없음'}, 'paper_ais': {}, 'full_market': {'universe': {}, 'quotes': {}, 'ranked': [], 'cursor': 0, 'last_scan_ts': 0, 'last_scan_text': '없음', 'stock_master_checked_at': 0, 'stock_master_source': '없음', 'status': '대기', 'errors': 0}, 'daytrade': {'date': '', 'cash': 0, 'trade_count': 0, 'position': None, 'market_mode': 'LEGACY_REMOVED', 'pending': None, 'trades': [], 'last_action': '구 구 단타 단타 제거'}, 'market_data_capture': {'last_candle_ts': 0, 'last_orderflow_ts': 0, 'last_investor_ts': 0, 'last_daily_ts': 0, 'last_metadata_ts': 0, 'last_audit_ts': 0, 'last_candle_minute': {}, 'seen_candle_keys': {}, 'last_trade_timestamp': {}, 'last_orderbook_timestamp': {}, 'latest_orderbook': {}, 'latest_trade': {}, 'price_timestamp': {}, 'calendar': {}, 'calendar_checked_at': 0, 'gate_ok': False, 'gate_reason': 'NOT_CHECKED', 'status': '대기', 'errors': 0}}

def now_kst():
    return datetime.now(KST)

def is_weekend_kst():
    """토요일(5), 일요일(6)이면 True."""
    return now_kst().weekday() >= 5

def today():
    return now_kst().strftime('%Y-%m-%d')

def now_text():
    return now_kst().strftime('%Y-%m-%d %H:%M:%S')

def now_short():
    return now_kst().strftime('%H:%M:%S')

def parse_api_datetime(value):
    """토스 ISO 8601 시각을 KST aware datetime으로 변환한다."""
    if not value:
        return None
    try:
        text = str(value).strip().replace('Z', '+00:00')
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        return dt.astimezone(KST)
    except Exception:
        return None

def data_age_seconds(value):
    dt = parse_api_datetime(value)
    if dt is None:
        return 10 ** 9
    return max(0.0, (now_kst() - dt).total_seconds())

def name_of(sym):
    if sym in ALL:
        return ALL.get(sym, sym)
    q = S.get('full_market', {}).get('quotes', {}).get(sym, {})
    return str(q.get('name') or sym)

def to_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            for key in ['krw', 'amount', 'value', 'cash', 'quantity']:
                if key in v:
                    return to_float(v[key], default)
            return default
        return float(str(v).replace(',', '').replace('원', '').replace('%', '').strip())
    except Exception:
        return default

def to_int(v, default=0):
    try:
        return int(to_float(v, default))
    except Exception:
        return default

def pct(a, b):
    try:
        if not b:
            return 0.0
        return (float(a) - float(b)) / float(b) * 100
    except Exception:
        return 0.0

def set_error(msg):
    print('[오류]', msg)
    with LOCK:
        S['last_error'] = f'{now_text()} {msg}'

def set_status(msg):
    with LOCK:
        S['status'] = msg
        S['updated'] = now_short()

def refresh_outbound_ip(force=False):
    """현재 Render 외부 송신 IP를 10분 캐시한다."""
    with LOCK:
        checked = float(S.get('outbound_ip_checked_at', 0) or 0)
    if not force and time.time() - checked < 600:
        return str(S.get('outbound_ip', '확인 전'))
    try:
        r = requests.get('https://api.ipify.org', timeout=5)
        ip = r.text.strip() if r.status_code == 200 else ''
        if not ip:
            raise RuntimeError(f'HTTP {r.status_code}')
        with LOCK:
            old = str(S.get('outbound_ip', '') or '')
            S['outbound_ip'] = ip
            S['outbound_ip_checked_at'] = time.time()
            S['outbound_ip_error'] = ''
            if old and old not in {'확인 전', ip}:
                S['last_error'] = f'{now_text()} 외부 IP 변경 {old} → {ip}'
        return ip
    except Exception as e:
        with LOCK:
            S['outbound_ip_checked_at'] = time.time()
            S['outbound_ip_error'] = str(e)[:200]
        return str(S.get('outbound_ip', '확인 실패'))

def refresh_kr_market_calendar(force=False):
    """공식 /api/v1/market-calendar/KR로 오늘 영업일과 정규장 시간을 캐시한다."""
    state = S.setdefault('market_data_capture', {})
    if not force and time.time() - to_float(state.get('calendar_checked_at', 0)) < MARKET_CALENDAR_REFRESH_SEC:
        return bool(state.get('calendar'))
    code, data = api_get('/api/v1/market-calendar/KR', params={'date': today()}, timeout=8)
    state['calendar_checked_at'] = time.time()
    if code != 200:
        state['calendar'] = {}
        state['gate_ok'] = False
        state['gate_reason'] = f'CALENDAR_HTTP_{code}'
        return False
    result = _result_dict(data)
    today_info = result.get('today', {}) if isinstance(result, dict) else {}
    integrated = today_info.get('integrated') if isinstance(today_info, dict) else None
    regular = integrated.get('regularMarket') if isinstance(integrated, dict) else None
    state['calendar'] = {'date': str(today_info.get('date', '')) if isinstance(today_info, dict) else '', 'is_business_day': bool(regular), 'regular_start': str(regular.get('startTime', '')) if isinstance(regular, dict) else '', 'regular_end': str(regular.get('endTime', '')) if isinstance(regular, dict) else '', 'auction_start': str(regular.get('singlePriceAuctionStartTime', '')) if isinstance(regular, dict) else ''}
    cal = state['calendar']
    if not cal.get('date') or cal.get('date') != today():
        state['gate_ok'] = False
        state['gate_reason'] = 'CALENDAR_NOT_TODAY'
    elif not cal.get('is_business_day'):
        state['gate_ok'] = False
        state['gate_reason'] = 'MARKET_CLOSED'
    else:
        start = parse_api_datetime(cal.get('regular_start'))
        end = parse_api_datetime(cal.get('regular_end'))
        if not start or not end:
            state['gate_ok'] = False
            state['gate_reason'] = 'REGULAR_SESSION_MISSING'
        elif not start <= now_kst() <= end:
            state['gate_ok'] = False
            state['gate_reason'] = 'OUTSIDE_REGULAR_SESSION'
        else:
            state['gate_ok'] = False
            state['gate_reason'] = 'WAITING_FRESH_DATA'
    return True

def regular_market_open_now():
    state = S.setdefault('market_data_capture', {})
    refresh_kr_market_calendar(False)
    cal = state.get('calendar', {})
    if not cal or cal.get('date') != today():
        return (False, 'CALENDAR_NOT_TODAY')
    if not cal.get('is_business_day'):
        return (False, 'MARKET_CLOSED')
    start = parse_api_datetime(cal.get('regular_start'))
    end = parse_api_datetime(cal.get('regular_end'))
    if not start or not end:
        return (False, 'REGULAR_SESSION_MISSING')
    n = now_kst()
    if not start <= n <= end:
        return (False, 'OUTSIDE_REGULAR_SESSION')
    return (True, 'OK')

def refresh_us_market_calendar(force=False):
    """공식 /api/v1/market-calendar/US의 KST 정규장 시간만 사용한다."""
    state = S.setdefault('us_market_data_capture', {})
    if not force and time.time() - to_float(state.get('calendar_checked_at', 0)) < MARKET_CALENDAR_REFRESH_SEC:
        return bool(state.get('calendar'))
    state['calendar_checked_at'] = time.time()
    chosen = None
    last_code = 0
    nowv = now_kst()
    for query_date in (today(), (nowv - timedelta(days=1)).date().isoformat()):
        code, data = api_get('/api/v1/market-calendar/US', params={'date': query_date}, timeout=8)
        last_code = code
        if code != 200:
            continue
        info = _result_dict(data).get('today', {})
        regular = info.get('regularMarket') if isinstance(info, dict) else None
        start = _parse_iso(regular.get('startTime')) if isinstance(regular, dict) else None
        end = _parse_iso(regular.get('endTime')) if isinstance(regular, dict) else None
        if start and end and (start <= nowv <= end + timedelta(hours=12)):
            chosen = (info, regular)
            break
    if not chosen:
        state['calendar'] = {}
        state['status'] = f'CALENDAR_HTTP_{last_code}' if last_code != 200 else 'MARKET_CLOSED'
        return False
    info, regular = chosen
    state['calendar'] = {'date': str(info.get('date', '')), 'is_business_day': bool(regular), 'regular_start': str(regular.get('startTime', '')) if isinstance(regular, dict) else '', 'regular_end': str(regular.get('endTime', '')) if isinstance(regular, dict) else ''}
    state['status'] = 'READY' if regular else 'MARKET_CLOSED'
    return bool(regular)

def us_regular_market_open_now():
    refresh_us_market_calendar(False)
    cal = S.setdefault('us_market_data_capture', {}).get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))
    if not cal.get('is_business_day') or not start or (not end):
        return (False, 'US_MARKET_CLOSED')
    return (start <= now_kst() <= end, 'OK' if start <= now_kst() <= end else 'OUTSIDE_US_REGULAR')

def market_safety_gate(require_orderbook_symbol=None):
    """가상/실거래 공통 차단. 휴장, 장외, 과거 가격, 오래된 호가를 거부한다."""
    if not ENABLE_MARKET_SAFETY_GATE:
        return (True, 'GATE_DISABLED')
    state = S.setdefault('market_data_capture', {})
    ok, reason = regular_market_open_now()
    if not ok:
        state['gate_ok'], state['gate_reason'] = (False, reason)
        return (False, reason)
    price_ts = state.get('price_timestamp', {})
    check_symbols = [require_orderbook_symbol] if require_orderbook_symbol else MARKET_DATA_CORE_SYMBOLS[:2]
    ages = [data_age_seconds(price_ts.get(sym)) for sym in check_symbols if sym]
    if not ages or min(ages) > MAX_PRICE_AGE_SEC:
        reason = 'STALE_PRICE'
        state['gate_ok'], state['gate_reason'] = (False, reason)
        return (False, reason)
    if require_orderbook_symbol and REQUIRE_FRESH_ORDERBOOK_FOR_PAPER:
        ob = state.get('latest_orderbook', {}).get(require_orderbook_symbol, {})
        if data_age_seconds(ob.get('timestamp')) > MAX_ORDERBOOK_AGE_SEC:
            reason = 'STALE_ORDERBOOK'
            state['gate_ok'], state['gate_reason'] = (False, reason)
            return (False, reason)
        if to_float(ob.get('best_ask', 0)) <= 0 or to_float(ob.get('best_bid', 0)) <= 0:
            reason = 'INVALID_ORDERBOOK'
            state['gate_ok'], state['gate_reason'] = (False, reason)
            return (False, reason)
    state['gate_ok'], state['gate_reason'] = (True, 'OK')
    return (True, 'OK')

def set_status_once(key, msg, cooldown=300):
    with LOCK:
        last = S['last_alert'].get(key, 0)
        if time.time() - last < cooldown:
            return
        S['last_alert'][key] = time.time()
    set_status(msg)

def day_dir():
    path = os.path.join(LOG_ROOT, today())
    os.makedirs(os.path.join(path, 'symbols'), exist_ok=True)
    return path

def summary_path():
    return os.path.join(day_dir(), f'summary_{today()}.csv')

def paper_path():
    return os.path.join(day_dir(), f'paper_trades_{today()}.csv')

def alert_log_path():
    return os.path.join(day_dir(), f'alert_log_{today()}.csv')

def backup_zip_path():
    os.makedirs(os.path.join(BACKUP_ROOT, 'KR'), exist_ok=True)
    return os.path.join(BACKUP_ROOT, 'KR', f'backup_KR_{today()}.zip')

def symbol_path(sym):
    return os.path.join(day_dir(), 'symbols', f'{sym}.csv')

def market_data_dir():
    path = os.path.join(day_dir(), 'market_data')
    os.makedirs(path, exist_ok=True)
    return path

def candle_1m_path(sym):
    return os.path.join(market_data_dir(), f'candles_1m_{sym}_{today()}.csv')

def price_snapshot_path(sym):
    return os.path.join(market_data_dir(), f'prices_{sym}_{today()}.csv')

def orderbook_path(sym):
    return os.path.join(market_data_dir(), f'orderbook_{sym}_{today()}.csv')

def trades_path(sym):
    return os.path.join(market_data_dir(), f'trades_{sym}_{today()}.csv')

def market_indicator_path():
    return os.path.join(market_data_dir(), f'market_indicators_{today()}.csv')

def investor_trading_path():
    return os.path.join(market_data_dir(), f'investor_trading_{today()}.csv')

def candle_daily_path(sym):
    return os.path.join(market_data_dir(), f'candles_1d_{sym}.csv')

def stock_metadata_path(sym):
    return os.path.join(market_data_dir(), f'stock_metadata_{sym}_{today()}.csv')

def multi_ai_state_path(ai_id):
    return os.path.join(day_dir(), 'paper_accounts', f'paper_account_state_{ai_id}_{today()}.json')

def data_quality_audit_path():
    return os.path.join(market_data_dir(), f'data_quality_audit_{today()}.csv')

def raw_api_error_path():
    return os.path.join(market_data_dir(), f'api_errors_{today()}.csv')

def raw_market_dir(market='KR'):
    market = str(market).upper()
    base = us_day_dir() if market == 'US' else day_dir()
    path = os.path.join(base, 'raw', market)
    os.makedirs(path, exist_ok=True)
    return path

def us_trade_date_from_calendar():
    cal = S.setdefault('us_market_data_capture', {}).get('calendar', {})
    return str(cal.get('date', '') or today())

def us_day_dir():
    path = os.path.join(LOG_ROOT, 'US', us_trade_date_from_calendar())
    os.makedirs(path, exist_ok=True)
    return path

def us_market_data_dir():
    path = os.path.join(us_day_dir(), 'market_data')
    os.makedirs(path, exist_ok=True)
    return path

def us_data_path(kind, sym=''):
    d = us_trade_date_from_calendar()
    suffix = f'_{sym}' if sym else ''
    return os.path.join(us_market_data_dir(), f'{kind}{suffix}_{d}.csv')

def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None

def _completed_session_candle(ts, session_date, session_start, session_end, now_value=None):
    """거래일·정규장·완성봉을 동시에 검증한다. endTime은 exclusive다."""
    dt = _parse_iso(ts)
    start = _parse_iso(session_start)
    end = _parse_iso(session_end)
    now_value = now_value or now_kst()
    if not dt or not start or (not end):
        return False
    if session_date and dt.astimezone(KST).date().isoformat() != str(session_date):
        return False
    current_minute = now_value.replace(second=0, microsecond=0)
    return start <= dt < end and dt < current_minute

def _read_csv_rows(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def _rewrite_csv(path, headers, rows):
    tmp = path + '.tmp'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow({h: row.get(h, '') for h in headers})
    os.replace(tmp, path)
    with CSV_KEY_LOCK:
        CSV_KEY_CACHE.pop(path, None)

def _next_ingest_seq():
    global INGEST_SEQ
    with INGEST_LOCK:
        INGEST_SEQ += 1
        return INGEST_SEQ

def _infer_market_from_params(params):
    p = params or {}
    symbols = str(p.get('symbols') or p.get('symbol') or '')
    for sym in [x.strip() for x in symbols.split(',') if x.strip()]:
        if sym in ALL or (len(sym) == 6 and sym[0].isdigit()):
            continue
        if sym.startswith('KR_') or sym in {'KOSPI', 'KOSDAQ'}:
            continue
        return 'US'
    return 'KR'

def _safe_json_dump(data):
    try:
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=str)
    except Exception:
        return json.dumps({'raw': str(data)}, ensure_ascii=False)

def write_raw_api_event(method, path, params, status, data, requested_at, received_at, elapsed_ms, headers=None):
    """원본 API 응답을 append-only JSONL로 보존한다."""
    if not ENABLE_RAW_API_CAPTURE:
        return ''
    market = _infer_market_from_params(params)
    seq = _next_ingest_seq()
    raw_id = f'{today()}-{seq:012d}-{uuid.uuid4().hex[:10]}'
    body = _safe_json_dump(data)
    if len(body) > RAW_API_MAX_BODY_CHARS:
        body = body[:RAW_API_MAX_BODY_CHARS] + '...TRUNCATED'
    row = {'raw_id': raw_id, 'ingest_seq': seq, 'method': method, 'path': path, 'params': params or {}, 'status': status, 'requested_at': requested_at, 'received_at': received_at, 'saved_at': now_text(), 'elapsed_ms': round(float(elapsed_ms), 3), 'rate_limit': {'limit': (headers or {}).get('X-RateLimit-Limit', ''), 'remaining': (headers or {}).get('X-RateLimit-Remaining', ''), 'reset': (headers or {}).get('X-RateLimit-Reset', ''), 'retry_after': (headers or {}).get('Retry-After', '')}, 'body': body}
    event_date = us_trade_date_from_calendar() if market == 'US' else today()
    filepath = os.path.join(raw_market_dir(market), f'api_{event_date}.jsonl')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    with LOCK:
        S.setdefault('last_api_meta', {})[path, str(params or {})] = {'raw_id': raw_id, 'ingest_seq': seq, 'requested_at': requested_at, 'received_at': received_at, 'elapsed_ms': elapsed_ms}
    return raw_id

def _load_csv_keys(path, key_fields):
    cache_key = (path, tuple(key_fields))
    with CSV_KEY_LOCK:
        if cache_key in CSV_KEY_CACHE:
            return CSV_KEY_CACHE[cache_key]
        keys = set()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                    for row in csv.DictReader(f):
                        keys.add(tuple((str(row.get(k, '')) for k in key_fields)))
            except Exception as e:
                set_error(f'CSV 중복키 로드 실패 {os.path.basename(path)}: {e}')
        CSV_KEY_CACHE[cache_key] = keys
        return keys

def write_row_unique(path, headers, row, key_fields):
    """CSV 재시작 후에도 유지되는 idempotent append."""
    key = tuple((str(row.get(k, '')) for k in key_fields))
    with CSV_KEY_LOCK:
        keys = _load_csv_keys(path, key_fields)
        if key in keys:
            return False
        try:
            exists = os.path.exists(path)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            with open(path, 'a', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=headers)
                if not exists:
                    w.writeheader()
                w.writerow({h: row.get(h, '') for h in headers})
            keys.add(key)
            return True
        except Exception as e:
            set_error(f'CSV 고유 저장 오류: {e}')
            return False

def _rate_wait_before_call(group):
    """같은 Rate Limit Group의 병렬 폭주를 호출 전에 막는다."""
    group = group or 'OTHER'
    with API_CALL_LOCK:
        now = time.monotonic()
        wait = max(0.0, RATE_NEXT_ALLOWED[group] - now)
        if wait > 0:
            time.sleep(wait)
        RATE_NEXT_ALLOWED[group] = time.monotonic() + RATE_MIN_GAP_SEC.get(group, RATE_MIN_GAP_SEC['OTHER'])

def _rate_penalize(group, seconds):
    with API_CALL_LOCK:
        RATE_NEXT_ALLOWED[group] = max(RATE_NEXT_ALLOWED[group], time.monotonic() + max(0.0, seconds))

def _apply_official_rate_headers(group, headers, status_code):
    """토스 공식 Rate Limit 응답 헤더를 다음 호출 시각에 반영한다."""
    headers = headers or {}
    limit = to_float(headers.get('X-RateLimit-Limit', 0), 0)
    remaining = to_float(headers.get('X-RateLimit-Remaining', -1), -1)
    reset = to_float(headers.get('X-RateLimit-Reset', 0), 0)
    retry_after = to_float(headers.get('Retry-After', 0), 0)
    if limit > 0:
        RATE_MIN_GAP_SEC[group] = max(RATE_MIN_GAP_SEC.get(group, RATE_MIN_GAP_SEC['OTHER']), 1.0 / limit)
    if status_code == 429:
        _rate_penalize(group, max(1.0, retry_after, reset))
    elif remaining == 0 and reset > 0:
        _rate_penalize(group, reset)

def write_row(path, headers, row):
    try:
        exists = os.path.exists(path)
        with open(path, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=headers)
            if not exists:
                w.writeheader()
            w.writerow({h: row.get(h, '') for h in headers})
    except Exception as e:
        set_error(f'CSV 저장 오류: {e}')

def write_alert_log(level, kind, sym, price, profit_rate, decision, reason, sent, response=''):
    row = {'time': now_text(), 'level': level, 'kind': kind, 'symbol': sym or '', 'name': name_of(sym) if sym else '', 'price': price or 0, 'profit_rate': round(to_float(profit_rate), 2), 'decision': decision or '', 'reason': reason or '', 'sent': bool(sent), 'response': str(response)[:300]}
    write_row(alert_log_path(), ['time', 'level', 'kind', 'symbol', 'name', 'price', 'profit_rate', 'decision', 'reason', 'sent', 'response'], row)

def _atomic_json_write(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + f'.{uuid.uuid4().hex}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

def save_state():
    """상태를 원자적으로 저장하고 직전 정상본을 .bak로 보존한다."""
    try:
        with LOCK:
            data = {'paper': S.get('paper', {}), 'paper_ais': S.get('paper_ais', {}), 'google_drive': S.get('google_drive', {}), 'us_backup_completed': S.get('us_backup_completed', {}), 'kr_backup_completed': S.get('kr_backup_completed', {})}
        if os.path.isfile(STATE_PATH):
            try:
                with open(STATE_PATH, 'r', encoding='utf-8') as f:
                    prev = json.load(f)
                _atomic_json_write(STATE_BAK_PATH, prev)
            except Exception:
                pass
        _atomic_json_write(STATE_PATH, data)
    except Exception as e:
        set_error(f'state 저장 실패: {e}')

def _load_state_file(path):
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None

def load_state():
    """주 상태가 손상되면 직전 정상 .bak를 자동 복구한다."""
    data = None
    primary_error = ''
    try:
        data = _load_state_file(STATE_PATH)
    except Exception as e:
        primary_error = str(e)
    if data is None:
        try:
            data = _load_state_file(STATE_BAK_PATH)
            if data is not None:
                _atomic_json_write(STATE_PATH, data)
                set_error('state 주파일 손상으로 .bak 자동복구' + (f': {primary_error}' if primary_error else ''))
        except Exception as e:
            set_error(f'state 백업 로드 실패: {e}')
            data = None
    if data is None:
        with LOCK:
            if S['paper'].get('start_cash', 0) <= 0:
                S['paper'] = {'start_cash': VIRTUAL_BASE_CASH, 'cash': VIRTUAL_BASE_CASH, 'positions': {}, 'trades': [], 'realized_pl': 0, 'asset': VIRTUAL_BASE_CASH, 'profit_rate': 0, 'last_action': '초기 1천만원'}
        return
    try:
        with LOCK:
            paper = data.get('paper')
            if isinstance(paper, dict):
                S['paper'].update(paper)
            paper_ais = data.get('paper_ais')
            if isinstance(paper_ais, dict):
                S['paper_ais'] = paper_ais
            drive_state = data.get('google_drive')
            if isinstance(drive_state, dict):
                S['google_drive'].update(drive_state)
            us_done = data.get('us_backup_completed')
            if isinstance(us_done, dict):
                S['us_backup_completed'] = us_done
            kr_done = data.get('kr_backup_completed')
            if isinstance(kr_done, dict):
                S['kr_backup_completed'] = kr_done
            if S['paper'].get('start_cash', 0) <= 0:
                S['paper'] = {'start_cash': VIRTUAL_BASE_CASH, 'cash': VIRTUAL_BASE_CASH, 'positions': {}, 'trades': [], 'realized_pl': 0, 'asset': VIRTUAL_BASE_CASH, 'profit_rate': 0, 'last_action': '초기 1천만원'}
    except Exception as e:
        set_error(f'state 적용 실패: {e}')

def telegram_enabled():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

def telegram_notify_time_open():
    if is_weekend_kst():
        return False
    sh, sm = parse_hhmm(TELEGRAM_NOTIFY_START, 8, 50)
    eh, em = parse_hhmm(TELEGRAM_NOTIFY_END, 15, 30)
    n = now_kst()
    return (sh, sm) <= (n.hour, n.minute) <= (eh, em)

def telegram_button(text, url):
    return {'text': text, 'url': url}

def send_telegram(msg, buttons=None, force=False):
    if not force and (not telegram_notify_time_open()):
        write_alert_log('SYSTEM', 'telegram', '', 0, 0, 'skipped', 'TELEGRAM_NOTIFY_TIME_CLOSED', False, msg.split('\n')[0])
        return (False, f'TELEGRAM 알림 시간 아님({TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END})')
    if not telegram_enabled():
        write_alert_log('SYSTEM', 'telegram', '', 0, 0, 'not_sent', 'TELEGRAM 설정 없음', False, 'missing token/chat_id')
        return (False, 'TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 없음')
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg[:3900], 'disable_web_page_preview': True}
    if buttons:
        payload['reply_markup'] = json.dumps({'inline_keyboard': buttons}, ensure_ascii=False)
    try:
        r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', data=payload, timeout=8)
        ok = r.status_code == 200
        write_alert_log('INFO', 'telegram', '', 0, 0, 'sent' if ok else 'failed', msg.split('\n')[0], ok, f'HTTP {r.status_code} {r.text[:300]}')
        return (ok, f'HTTP {r.status_code} {r.text[:300]}')
    except Exception as e:
        write_alert_log('ERROR', 'telegram', '', 0, 0, 'exception', msg.split('\n')[0], False, str(e))
        return (False, str(e))

def send_telegram_file(filepath, caption='', force=False):
    if not force and (not telegram_notify_time_open()):
        return (False, f'TELEGRAM 알림 시간 아님({TELEGRAM_NOTIFY_START}~{TELEGRAM_NOTIFY_END}, 주말 제외)')
    if not telegram_enabled():
        return (False, 'TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 없음')
    if not os.path.exists(filepath):
        return (False, f'파일 없음: {filepath}')
    try:
        with open(filepath, 'rb') as f:
            r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument', data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption[:1000]}, files={'document': (os.path.basename(filepath), f)}, timeout=30)
        ok = r.status_code == 200
        write_alert_log('INFO', 'telegram_file', '', 0, 0, 'sent' if ok else 'failed', caption, ok, f'HTTP {r.status_code} {r.text[:300]}')
        return (ok, f'HTTP {r.status_code} {r.text[:300]}')
    except Exception as e:
        write_alert_log('ERROR', 'telegram_file', '', 0, 0, 'exception', caption, False, str(e))
        return (False, str(e))

def get_token(force=False, stale_token=''):
    """토스 OAuth 토큰을 단일 스레드에서만 발급한다.

    client 당 유효 access token은 1개이므로, 여러 요청이 동시에 401을 받아도
    잠금 획득 후 다른 스레드가 이미 토큰을 교체했는지 다시 확인한다.
    """
    with TOKEN_REFRESH_LOCK:
        with LOCK:
            current = str(S.get('token', '') or '')
            exp = float(S.get('token_exp', 0) or 0)
        if stale_token and current and (current != stale_token) and (time.time() < exp):
            return current
        if not force and current and (time.time() < exp):
            return current
        return _get_token_locked()

def _get_token_locked():
    if not CLIENT_ID or not CLIENT_SECRET:
        set_status('토스 키 없음')
        return ''
    try:
        r = requests.post(BASE + '/oauth2/token', data={'grant_type': 'client_credentials', 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET}, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        data = r.json() if r.text else {}
        if r.status_code != 200:
            raw = str(data).replace('\n', ' ')[:800]
            with LOCK:
                S['token_last_error'] = raw
            if r.status_code == 403 and ('IP address not allowed' in raw or 'access_denied' in raw):
                ip = refresh_outbound_ip(True)
                set_status(f'IP 차단: {ip}')
                set_error(f'토스 허용 IP 아님: {ip} / {raw}')
            else:
                set_status(f'토큰 오류 {r.status_code}')
                set_error(f'토큰 오류: {raw}')
            return ''
        token = str(data.get('access_token', '') or '')
        expires_in = int(data.get('expires_in', 86400) or 86400)
        if not token:
            set_error('토큰 응답에 access_token 없음')
            return ''
        with LOCK:
            S['token'] = token
            S['token_exp'] = time.time() + max(60, expires_in - 300)
            S['token_last_error'] = ''
        set_status('토큰 정상')
        return token
    except Exception as e:
        set_error(f'토큰 예외: {e}')
        return ''

def ensure_token():
    with LOCK:
        token = str(S.get('token', '') or '')
        exp = float(S.get('token_exp', 0) or 0)
    if not token or time.time() >= exp:
        return get_token(force=False)
    return token

def clear_token(expected_token=''):
    """실패한 토큰이 아직 현재 토큰일 때만 폐기한다."""
    with LOCK:
        current = str(S.get('token', '') or '')
        if expected_token and current and (current != expected_token):
            return
        S['token'] = ''
        S['token_exp'] = 0

def auth_headers(account=False):
    """데이터 수집 전용 인증 헤더. 실계좌 헤더는 이 빌드에서 사용하지 않는다."""
    token = ensure_token() or ''
    return {'Authorization': 'Bearer ' + token}

def _json_or_raw(resp):
    try:
        return resp.json()
    except Exception:
        return {'raw': resp.text}

def _api_error_code(data):
    if not isinstance(data, dict):
        return ''
    error = data.get('error', {})
    if isinstance(error, dict):
        return str(error.get('code', '') or '').strip().lower()
    return ''

def _is_invalid_token(status_code, data):
    """401 중 공식 토큰 오류 두 종류만 재발급 대상으로 본다."""
    if status_code != 401:
        return False
    return _api_error_code(data) in {'invalid-token', 'expired-token'}

def api_get(path, params=None, account=False, timeout=10):
    """토스 GET 공통 호출.
    - 401: 단일 토큰 재발급 후 재시도
    - 429: Retry-After + 지수 백오프 + jitter
    - 모든 호출: 요청/수신/저장시각, rate-limit 헤더, 원본 응답 보존
    기존 호출부 호환을 위해 (status_code, data) 2개만 반환한다.
    """
    last_data = {}
    group = _rate_group_for_path(path)
    for attempt in range(4):
        _rate_wait_before_call(group)
        requested_at = now_kst().isoformat()
        t0 = time.time()
        try:
            request_headers = auth_headers(account)
            used_token = str(request_headers.get('Authorization', '')).replace('Bearer ', '', 1)
            r = requests.get(BASE + path, headers=request_headers, params=params or {}, timeout=timeout)
            received_at = now_kst().isoformat()
            elapsed_ms = (time.time() - t0) * 1000.0
            data = _json_or_raw(r)
            last_data = data
            raw_id = write_raw_api_event('GET', path, params or {}, r.status_code, data, requested_at, received_at, elapsed_ms, dict(r.headers))
            RATE_STATE[group] = {'status': r.status_code, 'limit': r.headers.get('X-RateLimit-Limit', ''), 'remaining': r.headers.get('X-RateLimit-Remaining', ''), 'reset': r.headers.get('X-RateLimit-Reset', ''), 'retry_after': r.headers.get('Retry-After', ''), 'updated_at': received_at, 'raw_id': raw_id}
            _apply_official_rate_headers(group, dict(r.headers), r.status_code)
            if _is_invalid_token(r.status_code, data):
                # 토큰 오류는 무한/장시간 반복하지 않는다.
                # 1회 강제 재발급 후 새 토큰으로 딱 한 번만 재시도하고,
                # 재발급 실패 또는 재시도 후 다시 401이면 즉시 호출자에게 반환한다.
                clear_token(expected_token=used_token)
                refreshed = get_token(force=True, stale_token=used_token)
                if not refreshed:
                    set_status('토큰 재발급 실패')
                    return (r.status_code, data)
                if attempt == 0:
                    time.sleep(0.2 + random.random() * 0.15)
                    continue
                set_status('토큰 재발급 후에도 401')
                return (r.status_code, data)
            if r.status_code == 429:
                retry_after = to_float(r.headers.get('Retry-After', 0), 0)
                reset = to_float(r.headers.get('X-RateLimit-Reset', 0), 0)
                wait = max(1.0, retry_after, reset, float(2 ** attempt)) + random.uniform(0.05, 0.35)
                _rate_penalize(group, wait)
                write_row(raw_api_error_path(), ['time', 'method', 'path', 'status', 'attempt', 'response'], {'time': now_text(), 'method': 'GET', 'path': path, 'status': 429, 'attempt': attempt + 1, 'response': str(data)[:1000]})
                if attempt < 3:
                    time.sleep(wait)
                    continue
                set_status(f'토스 요청 제한 대기: {group}')
                return (r.status_code, data)
            if r.status_code >= 500 and attempt < 3:
                time.sleep(2 ** attempt * 0.5 + random.uniform(0.05, 0.25))
                continue
            if r.status_code >= 400:
                write_row(raw_api_error_path(), ['time', 'method', 'path', 'status', 'attempt', 'response'], {'time': now_text(), 'method': 'GET', 'path': path, 'status': r.status_code, 'attempt': attempt + 1, 'response': str(data)[:1000]})
                set_error(f'GET {path} {r.status_code}: {str(data)[:300]}')
            return (r.status_code, data)
        except Exception as e:
            received_at = now_kst().isoformat()
            elapsed_ms = (time.time() - t0) * 1000.0
            last_data = {'error': str(e)}
            write_raw_api_event('GET', path, params or {}, 0, last_data, requested_at, received_at, elapsed_ms, {})
            if attempt < 3:
                time.sleep(2 ** attempt * 0.5 + random.uniform(0.05, 0.25))
                continue
            set_error(f'GET {path} 예외: {e}')
    return (0, last_data)

def first_list(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ['result', 'accounts', 'items', 'data']:
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ['accounts', 'items', 'list']:
                if isinstance(v.get(k2), list):
                    return v[k2]
    return []

def load_prices():
    code, data = api_get('/api/v1/prices', params={'symbols': ','.join(ALL.keys())}, timeout=15)
    if code != 200:
        set_status('현재가 오류')
        return False
    items = first_list(data)
    cnt = 0
    with LOCK:
        for item in items:
            sym = str(item.get('symbol', item.get('code', '')))
            price = 0
            for k in ['lastPrice', 'price', 'currentPrice', 'closePrice', 'tradePrice']:
                if k in item:
                    price = to_float(item[k])
                    break
            if sym not in ALL or price <= 0:
                continue
            api_ts = str(item.get('timestamp', ''))
            api_dt = parse_api_datetime(api_ts)
            if ENABLE_MARKET_SAFETY_GATE and api_dt and (api_dt.strftime('%Y-%m-%d') != today()):
                continue
            S.setdefault('market_data_capture', {}).setdefault('price_timestamp', {})[sym] = api_ts
            old = S['prices'].get(sym, price)
            S['prev_prices'][sym] = old
            S['prices'][sym] = price
            hist = S['history'].setdefault(sym, [])
            hist.append(price)
            if len(hist) > TARGET_PATTERN_LOOKBACK_POINTS:
                del hist[:-TARGET_PATTERN_LOOKBACK_POINTS]
            S['high'][sym] = max(S['high'].get(sym, price), price)
            S['low'][sym] = min(S['low'].get(sym, price), price)
            cnt += 1
        S['updated'] = now_short()
        S['status'] = f'정상 ({cnt}/{len(ALL)})'
    return cnt > 0

def wma(values, n):
    if len(values) < n:
        return None
    recent = values[-n:]
    weights = list(range(1, n + 1))
    return sum((v * w for v, w in zip(recent, weights))) / sum(weights)

def calc_wma_all():
    with LOCK:
        for sym in ALL:
            hist = S['history'].get(sym, [])
            p = S['prices'].get(sym, 0)
            old = S['wma'].get(sym, {})
            w5, w20, w60 = (wma(hist, 5), wma(hist, 20), wma(hist, 60))
            S['wma'][sym] = {'wma5': round(w5, 2) if w5 is not None else None, 'wma20': round(w20, 2) if w20 is not None else None, 'wma60': round(w60, 2) if w60 is not None else None, 'volume_ratio': old.get('volume_ratio', 1.0)}

def price_change_pct(sym):
    p = S['prices'].get(sym, 0)
    prev = S['prev_prices'].get(sym, p)
    return pct(p, prev)

def high_drop_pct(sym):
    p = S['prices'].get(sym, 0)
    h = S['high'].get(sym, p)
    return pct(p, h)

def low_rise_pct(sym):
    p = S['prices'].get(sym, 0)
    l = S['low'].get(sym, p)
    return pct(p, l)

def volume_ratio(sym):
    return S['wma'].get(sym, {}).get('volume_ratio', 1.0)

def hhmm_tuple(hhmm):
    h, m = parse_hhmm(hhmm)
    return (h, m)

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
    sh, sm = hhmm_tuple(PAPER_AUTO_START)
    eh, em = hhmm_tuple(PAPER_AUTO_END)
    n = now_kst()
    cur = (n.hour, n.minute)
    return cur >= (sh, sm) and cur <= (eh, em)

def record_paper_wait_once(reason, mode):
    key = f'PAPER_WAIT_{mode}_{reason}'
    with LOCK:
        last = S['last_alert'].get(key, 0)
        if time.time() - last < PAPER_WAIT_LOG_COOLDOWN_SEC:
            return False
        S['last_alert'][key] = time.time()
    record_paper('AI자동관망', '', 0, 0, reason, strategy='WAIT', mode=mode, source='AUTO')
    return True

def is_inverse_symbol(sym):
    return sym in INVERSE_SYMBOLS or '인버스' in name_of(sym)

def symbol_strength(sym):
    price = S['prices'].get(sym, 0)
    if price <= 0:
        return 0
    score = to_float(S['signals'].get(sym, {}).get('score', raw_symbol_score(sym)))
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
    core = [LEV, HYNIX, '494310', '488080', '469150']
    strong = 0
    for sym in core:
        score = to_float(S['signals'].get(sym, {}).get('score', raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        lrise = low_rise_pct(sym)
        if score >= 65 or chg >= 0.3 or lrise >= 1.0:
            strong += 1
    inverse_weak = True
    for sym in [INV, '252670', '0193L0']:
        score = to_float(S['signals'].get(sym, {}).get('score', raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        if score >= 62 and chg > 0:
            inverse_weak = False
    return strong >= 2 and inverse_weak

def inverse_market_confirmed():
    weak_long = 0
    for sym in [LEV, HYNIX, '494310', '488080', '122630', '069500', '233740']:
        score = to_float(S['signals'].get(sym, {}).get('score', raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        hdrop = high_drop_pct(sym)
        if score <= 45 or chg <= -0.3 or hdrop <= -1.5:
            weak_long += 1
    strong_inv = 0
    for sym in INVERSE_SYMBOLS:
        score = to_float(S['signals'].get(sym, {}).get('score', raw_symbol_score(sym)))
        chg = price_change_pct(sym)
        lrise = low_rise_pct(sym)
        if score >= 58 and (chg > 0 or lrise >= 0.7):
            strong_inv += 1
    return weak_long >= 4 and strong_inv >= 1

def operating_market_mode():
    market_total = to_float(S['market_score'].get('total', 50))
    label = S['market_score'].get('label', '')
    if semiconductor_strong() and market_total >= 42:
        return 'SEMI_LEADER_UP'
    if inverse_market_confirmed() and (market_total <= 42 or label == '하락장'):
        return 'DOWN'
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
    if market_total >= 65 or label == '상승장':
        return 'UP'
    if movers >= 3 and ups >= 1 and (downs >= 1):
        return 'CHOPPY'
    return 'NO_TRADE'

def choose_best_symbol(candidates):
    valid = []
    for sym in candidates:
        price = S['prices'].get(sym, 0)
        if price <= 0:
            continue
        if price_volume_risk_detected(sym):
            continue
        valid.append((symbol_strength(sym), sym))
    if not valid:
        return None
    valid.sort(reverse=True)
    return valid[0][1]

def raw_symbol_score(sym):
    price = S['prices'].get(sym, 0)
    if price <= 0:
        return 0
    wm = S['wma'].get(sym, {})
    w5, w20, w60 = (wm.get('wma5', 0), wm.get('wma20', 0), wm.get('wma60', 0))
    vr = wm.get('volume_ratio', 1)
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    lrise = low_rise_pct(sym)
    score = 50
    if w5 and price > w5:
        score += 10
    elif w5 and price < w5:
        score -= 10
    if w5 and w20 and (w5 > w20):
        score += 12
    elif w5 and w20 and (w5 < w20):
        score -= 12
    if w20 and w60 and (w20 > w60):
        score += 6
    elif w20 and w60 and (w20 < w60):
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
    kospi_base = raw_symbol_score('069500')
    kospi_lev = raw_symbol_score('122630')
    kospi_inv = raw_symbol_score('252670')
    kosdaq_base = raw_symbol_score('229200')
    kosdaq_lev = raw_symbol_score('233740')
    kosdaq_inv = raw_symbol_score('251340')
    kospi_score = int((kospi_base + kospi_lev) / 2 - (kospi_inv - 50) * 0.4)
    kosdaq_score = int((kosdaq_base + kosdaq_lev) / 2 - (kosdaq_inv - 50) * 0.4)
    total = int((kospi_score + kosdaq_score) / 2)
    label = '상승장' if total >= 65 else '하락장' if total <= 40 else '혼조/관망'
    with LOCK:
        S['market_score'] = {'kospi': max(0, min(100, kospi_score)), 'kosdaq': max(0, min(100, kosdaq_score)), 'total': max(0, min(100, total)), 'label': label}

def calc_symbol_score(sym):
    score = raw_symbol_score(sym)
    if score <= 0:
        return 0
    # 뉴스 엔진은 제거했다. 가상전략 점수는 수집된 가격/거래량/시장 데이터만 사용한다.
    market_total = S['market_score'].get('total', 50)
    is_inverse = '인버스' in name_of(sym)
    if is_inverse:
        score += int((50 - market_total) * 0.25)
    else:
        score += int((market_total - 50) * 0.25)
    if sym == LEV:
        hynix_chg = price_change_pct(HYNIX)
        score += 8 if hynix_chg > 0 else -8 if hynix_chg < 0 else 0
    if sym == INV:
        hynix_chg = price_change_pct(HYNIX)
        score += 8 if hynix_chg < 0 else -8 if hynix_chg > 0 else 0
    return max(0, min(100, int(score)))

def price_volume_risk_detected(sym):
    """가격·거래량 급락 위험만 판정한다. 외부 뉴스 의존 없음."""
    chg = price_change_pct(sym)
    hdrop = high_drop_pct(sym)
    vr = volume_ratio(sym)
    return chg <= -1.0 and hdrop <= -3.0 and vr >= 1.8

def signal_label(sym, score):
    if price_volume_risk_detected(sym):
        return '악재성 급락 의심 ⚠️'
    if score >= 80:
        return '강한 진입 ⭕'
    if score >= 70:
        return '진입 후보 ⭕'
    if score >= 60:
        return '보유/관찰 🟡'
    if score >= 40:
        return '관망 🔴'
    if high_drop_pct(sym) <= -3 or volume_ratio(sym) >= 1.8:
        return '매도 후보 ⛔'
    return '약함 🔴'

def recommend_ratio(score):
    if score >= 85:
        return min(MAX_BUY_RATIO, 0.7)
    if score >= 75:
        return min(MAX_BUY_RATIO, 0.5)
    if score >= 65:
        return min(MAX_BUY_RATIO, 0.3)
    return 0.0

def build_signal(sym):
    """가상전략용 신호만 만든다. 실계좌 현금/매도가능수량은 참조하지 않는다."""
    score = S['scores'].get(sym, 0)
    ratio = recommend_ratio(score)
    return {'label': signal_label(sym, score), 'score': score, 'ratio': ratio, 'qty': 0, 'rec_buy_qty': 0, 'rec_sell_qty': 0, 'hdrop': round(high_drop_pct(sym), 2), 'lrise': round(low_rise_pct(sym), 2), 'chg': round(price_change_pct(sym), 2), 'volume_ratio': round(volume_ratio(sym), 2)}

def calc_scores():
    calc_market_direction()
    with LOCK:
        for sym in ALL:
            S['scores'][sym] = calc_symbol_score(sym)
        for sym in ALL:
            S['signals'][sym] = build_signal(sym)

def target_market_regime():
    """시장상황 분류: RECOVERY/UP/DOWN/CHOPPY/NO_TRADE.
    점수형 매수는 쓰지 않고, 롱/인버스 그룹의 실제 흐름으로 먼저 분류한다.
    """
    long_syms = [LEV, '494310', '0193W0', '122630', '233740']
    inv_syms = ['252670', '251340', INV, '0193L0']

    def avg_change(syms):
        vals = [price_change_pct(s) for s in syms if S['prices'].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    def avg_low_rise(syms):
        vals = [low_rise_pct(s) for s in syms if S['prices'].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    def avg_high_drop(syms):
        vals = [high_drop_pct(s) for s in syms if S['prices'].get(s, 0) > 0]
        return sum(vals) / len(vals) if vals else 0
    long_chg = avg_change(long_syms)
    inv_chg = avg_change(inv_syms)
    long_drop = avg_high_drop(long_syms)
    inv_drop = avg_high_drop(inv_syms)
    long_rise = avg_low_rise(long_syms)
    if inv_chg >= 0.4 and long_chg <= -0.25 and (long_drop <= -1.0):
        return 'DOWN'
    if long_chg >= 0.35 and inv_chg <= 0.2:
        return 'UP'
    if long_drop <= -TARGET_LONG_PULLBACK_PCT and long_rise >= 2.0 and (inv_chg < 1.0):
        return 'RECOVERY'
    movers = sum((1 for s in long_syms + inv_syms if abs(price_change_pct(s)) >= 0.3))
    mixed = long_chg > 0 and inv_chg > 0 or (long_chg < 0 and inv_chg < 0)
    if movers >= 3 and mixed:
        return 'CHOPPY'
    return 'NO_TRADE'

def parse_hhmm(s, default_h=15, default_m=20):
    try:
        h, m = str(s).split(':')
        return (int(h), int(m))
    except Exception:
        return (default_h, default_m)

def time_after_hhmm(hhmm):
    h, m = parse_hhmm(hhmm)
    n = now_kst()
    return (n.hour, n.minute) >= (h, m)

def paper_total_asset():
    with LOCK:
        total = S['paper'].get('cash', 0)
        positions = dict(S['paper'].get('positions', {}))
        prices = dict(S['prices'])
    for sym, pos in positions.items():
        total += to_float(pos.get('qty', 0)) * prices.get(sym, to_float(pos.get('avg', 0)))
    return int(total)

def update_paper_asset():
    with LOCK:
        asset = paper_total_asset()
        S['paper']['asset'] = asset
        start = S['paper'].get('start_cash', 0)
        S['paper']['profit_rate'] = pct(asset, start) if start else 0

def record_paper(action, sym, price, qty, reason, pl=0, strategy='', mode='', source='AUTO'):
    update_paper_asset()
    with LOCK:
        row = {'time': now_short(), 'source': source, 'strategy': strategy, 'market_mode': mode or S.get('daytrade', {}).get('market_mode', ''), 'action': action, 'symbol': sym, 'name': name_of(sym), 'price': price, 'qty': qty, 'pl': pl, 'reason': reason, 'asset': S['paper'].get('asset', 0)}
        S['paper']['trades'].insert(0, row)
        S['paper']['trades'] = S['paper']['trades'][:100]
    write_row(paper_path(), ['time', 'source', 'strategy', 'market_mode', 'action', 'symbol', 'name', 'price', 'qty', 'pl', 'reason', 'asset'], row)
    save_state()

def paper_invested_amount():
    with LOCK:
        positions = dict(S['paper'].get('positions', {}))
        prices = dict(S['prices'])
    total = 0
    for sym, pos in positions.items():
        total += to_float(pos.get('qty', 0)) * prices.get(sym, to_float(pos.get('avg', 0)))
    return int(total)

def paper_buy_amount(sym, amount, reason, strategy='SWING', mode=''):
    if sym not in ALL:
        return False
    price = S['prices'].get(sym, 0)
    if price <= 0 or amount <= 0:
        return False
    with LOCK:
        cash = to_int(S['paper'].get('cash', 0))
    spendable = max(0, cash - MIN_DEFENSE_CASH)
    amount = min(int(amount), spendable)
    if amount <= 0:
        return False
    qty = int(amount // price)
    if qty <= 0:
        return False
    cost = qty * price
    with LOCK:
        pos = S['paper']['positions'].get(sym, {'qty': 0, 'avg': 0, 'stage': 0, 'strategy': strategy})
        old_qty = to_float(pos.get('qty', 0))
        old_avg = to_float(pos.get('avg', 0))
        new_qty = old_qty + qty
        new_avg = (old_qty * old_avg + cost) / new_qty if new_qty else price
        stage = min(3, int(to_float(pos.get('stage', 0))) + 1)
        S['paper']['cash'] -= cost
        S['paper']['positions'][sym] = {'qty': new_qty, 'avg': new_avg, 'buy_time': pos.get('buy_time') or now_text(), 'high_after_buy': max(to_float(pos.get('high_after_buy', 0)), price, new_avg), 'stage': stage, 'strategy': strategy}
        S['paper']['last_action'] = f'{now_short()} AI 자동가상매수 {name_of(sym)} {stage}단계'
    record_paper('AI자동가상매수', sym, price, qty, reason, strategy=strategy, mode=mode or operating_market_mode(), source='AUTO')
    return True

def paper_sell(sym, ratio, reason):
    with LOCK:
        pos = S['paper']['positions'].get(sym)
        price = S['prices'].get(sym, 0)
    if not pos or price <= 0:
        return False
    have = int(to_float(pos.get('qty', 0)))
    qty = have if ratio >= 1 else int(have * ratio)
    if qty <= 0:
        return False
    proceeds = qty * price
    avg = to_float(pos.get('avg', 0))
    pl = int((price - avg) * qty)
    with LOCK:
        S['paper']['cash'] += proceeds
        S['paper']['realized_pl'] += pl
        remain = have - qty
        if remain <= 0:
            S['paper']['positions'].pop(sym, None)
        else:
            S['paper']['positions'][sym] = {'qty': remain, 'avg': avg, 'buy_time': pos.get('buy_time', ''), 'high_after_buy': pos.get('high_after_buy', avg)}
        S['paper']['last_action'] = f'{now_short()} 가상매도 {name_of(sym)}'
    record_paper('수동가상매도', sym, price, qty, reason, pl, strategy='MANUAL', mode=operating_market_mode(), source='MANUAL')
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
        S['daytrade']['market_mode'] = mode
    if not ENABLE_PAPER_AUTO:
        update_paper_asset()
        return
    if not paper_auto_time_open():
        update_paper_asset()
        return
    with LOCK:
        positions = dict(S['paper'].get('positions', {}))
        prices = dict(S['prices'])
    for sym, pos in list(positions.items()):
        price = prices.get(sym, 0)
        avg = to_float(pos.get('avg', 0))
        if price <= 0 or avg <= 0:
            continue
        high = max(to_float(pos.get('high_after_buy', avg)), price)
        stage = int(to_float(pos.get('stage', 1)))
        strategy = pos.get('strategy', 'SWING')
        with LOCK:
            if sym in S['paper']['positions']:
                S['paper']['positions'][sym]['high_after_buy'] = high
        profit = pct(price, avg)
        drop = pct(price, high) if high else 0
        sell_reason = ''
        if profit <= -3.0:
            sell_reason = f'AI 자동 손절 {profit:.2f}%'
        elif is_inverse_symbol(sym) and mode in ['UP', 'SEMI_LEADER_UP']:
            sell_reason = 'AI 자동매도: 인버스 보유 중 상승/반도체 주도 전환'
        elif not is_inverse_symbol(sym) and mode == 'DOWN':
            sell_reason = 'AI 자동매도: 롱 보유 중 DOWN 전환'
        elif is_after_or_equal_hhmm(NO_NEW_BUY_AFTER) and profit >= 1.0 and (drop <= -1.5):
            sell_reason = f'AI 자동 수익보호: 14:30 이후 고점대비 {drop:.2f}%'
        elif profit >= 1.0 and drop <= -3.0:
            sell_reason = f'AI 자동 추적익절: 고점대비 {drop:.2f}%'
        elif strategy == 'DAYTRADE' and time_after_hhmm(PAPER_DAYTRADE_FORCE_EXIT_TIME):
            sell_reason = 'AI 자동 단타 15:20 전 정리'
        if sell_reason:
            paper_sell(sym, 1.0, sell_reason)
            continue
        invested = paper_invested_amount()
        if not buy_time_blocked() and strategy == 'SWING' and (mode in ['SEMI_LEADER_UP', 'UP']) and (stage < 3) and (invested < SWING_MAX_EXPOSURE):
            if profit >= 0.5 or symbol_strength(sym) >= 72:
                next_amount = SWING_BUY_STEP_AMOUNTS[min(stage, 2)]
                paper_buy_amount(sym, next_amount, f'AI 자동 추가매수 {stage + 1}단계: {mode} 강세 유지', strategy='SWING', mode=mode)
    with LOCK:
        has = bool(S['paper'].get('positions'))
    if has:
        update_paper_asset()
        save_state()
        return
    if buy_time_blocked():
        record_paper_wait_once('09:05 전 또는 14:30 이후 신규 가상매수 금지', mode)
        update_paper_asset()
        return
    if mode in ['CHOPPY', 'NO_TRADE']:
        record_paper_wait_once(f'{mode}: 방향 없음, 가상매수 안 함', mode)
        update_paper_asset()
        return
    if mode == 'SEMI_LEADER_UP':
        sym = choose_best_symbol(SEMI_LONG_SYMBOLS)
        if sym:
            paper_buy_amount(sym, SWING_BUY_STEP_AMOUNTS[0], f'AI 자동 스윙 1차: 반도체 주도장 {sym}', strategy='SWING', mode=mode)
    elif mode == 'UP':
        sym = choose_best_symbol(UP_LONG_SYMBOLS)
        if sym:
            paper_buy_amount(sym, SWING_BUY_STEP_AMOUNTS[0], f'AI 자동 롱 1차: 상승장 {sym}', strategy='SWING', mode=mode)
    elif mode == 'DOWN':
        if not semiconductor_strong():
            sym = choose_best_symbol(INVERSE_SYMBOLS)
            if sym:
                paper_buy_amount(sym, min(5000000, INVERSE_MAX_EXPOSURE), f'AI 자동 인버스 단타: DOWN {sym}', strategy='DAYTRADE', mode=mode)
    update_paper_asset()
    save_state()

def _ranking_result(data):
    if not isinstance(data, dict):
        return ({}, [])
    result = data.get('result')
    if not isinstance(result, dict):
        return ({}, [])
    rankings = result.get('rankings')
    if not isinstance(rankings, list):
        rankings = []
    return (result, rankings)

def _ranking_change_pct(item):
    price = item.get('price') if isinstance(item, dict) else {}
    if not isinstance(price, dict):
        return 0.0
    return to_float(price.get('changeRate'), 0.0) * 100.0

def _ranking_last_price(item):
    price = item.get('price') if isinstance(item, dict) else {}
    if not isinstance(price, dict):
        return 0.0
    return to_float(price.get('lastPrice'), 0.0)

def _stock_info_map(symbols):
    """랭킹 후보의 종목명·시장·상장상태를 최대 200개 단위로 보강한다."""
    result = {}
    clean = [str(x).strip() for x in symbols if str(x).strip()]
    for i in range(0, len(clean), 200):
        batch = clean[i:i + 200]
        code, data = api_get('/api/v1/stocks', params={'symbols': ','.join(batch)}, timeout=15)
        if code != 200:
            continue
        for item in first_list(data):
            if not isinstance(item, dict):
                continue
            sym = str(item.get('symbol') or '').strip()
            if not sym:
                continue
            result[sym] = {'symbol': sym, 'name': str(item.get('name') or sym).strip(), 'market': str(item.get('market') or '').strip(), 'security_type': str(item.get('securityType') or '').strip(), 'currency': str(item.get('currency') or '').strip(), 'listing_status': str(item.get('status') or '').strip(), 'trading_suspended': bool((item.get('koreanMarketDetail') or {}).get('krxTradingSuspended') if isinstance(item.get('koreanMarketDetail'), dict) else False)}
    return result

def load_full_market_universe(force=False):
    """토스 랭킹 API로 현재 시장 후보군을 자동 구성한다.

    전체 상장종목 마스터를 빈 symbols로 요청하지 않는다.
    시장 거래대금·거래량·상승·하락 랭킹을 합쳐 G01~G05 후보군으로 사용한다.
    """
    state = S.setdefault('full_market', {})
    now_ts = time.time()
    if state.get('universe') and (not force) and (now_ts - to_float(state.get('stock_master_checked_at', 0)) < FULL_MARKET_SCAN_INTERVAL_SEC):
        return state['universe']
    merged = {}
    errors = []
    ranked_at_values = []
    for ranking_type in FULL_MARKET_RANKING_TYPES:
        duration = '1d' if ranking_type in {'TOP_GAINERS', 'TOP_LOSERS'} else 'realtime'
        params = {'type': ranking_type, 'marketCountry': 'KR', 'duration': duration, 'excludeInvestmentCaution': True, 'count': max(1, min(100, FULL_MARKET_RANKING_COUNT))}
        code, data = api_get('/api/v1/rankings', params=params, timeout=15)
        if code != 200:
            errors.append(f'{ranking_type}:HTTP_{code}')
            continue
        result, rankings = _ranking_result(data)
        ranked_at = str(result.get('rankedAt') or '')
        if ranked_at:
            ranked_at_values.append(ranked_at)
        for item in rankings:
            if not isinstance(item, dict):
                continue
            sym = str(item.get('symbol') or '').strip()
            if not sym or sym in FULL_MARKET_BLOCKED_SYMBOLS:
                continue
            currency = str(item.get('currency') or '').upper()
            if currency and currency != 'KRW':
                continue
            row = merged.setdefault(sym, {'symbol': sym, 'name': sym, 'market': '', 'security_type': '', 'currency': currency or 'KRW', 'listing_status': '', 'ranking_types': [], 'ranking_best': {}, 'price': 0.0, 'change_pct': 0.0, 'volume': 0.0, 'turnover': 0.0, 'timestamp': ranked_at})
            row['ranking_types'].append(ranking_type)
            row['ranking_best'][ranking_type] = int(to_float(item.get('rank'), 9999))
            row['price'] = max(to_float(row.get('price'), 0), _ranking_last_price(item))
            row['change_pct'] = _ranking_change_pct(item)
            row['volume'] = max(to_float(row.get('volume'), 0), to_float(item.get('tradingVolume'), 0))
            row['turnover'] = max(to_float(row.get('turnover'), 0), to_float(item.get('tradingAmount'), 0))
            if ranked_at:
                row['timestamp'] = ranked_at
    symbols = list(merged)
    info_map = _stock_info_map(symbols)
    universe = {}
    for sym, row in merged.items():
        info = info_map.get(sym, {})
        if info:
            if str(info.get('currency') or 'KRW').upper() != 'KRW':
                continue
            if str(info.get('listing_status') or 'ACTIVE').upper() not in {'ACTIVE', ''}:
                continue
            if info.get('trading_suspended'):
                continue
            row.update(info)
        if to_float(row.get('price'), 0) < FULL_MARKET_MIN_PRICE:
            continue
        if to_float(row.get('turnover'), 0) and to_float(row.get('turnover'), 0) < FULL_MARKET_MIN_TURNOVER:
            continue
        universe[sym] = row
    state['universe'] = universe
    state['stock_master_checked_at'] = now_ts
    state['stock_master_source'] = 'TOSS_/api/v1/rankings'
    state['ranking_last_at'] = max(ranked_at_values) if ranked_at_values else ''
    state['ranking_errors'] = errors
    state['status'] = f'토스 전체시장 랭킹 후보 {len(universe):,}개 로드' if universe else 'FULL_MARKET_UNIVERSE_EMPTY / ' + (', '.join(errors) if errors else 'RANKINGS_EMPTY')
    return universe

def _quote_field(item, keys, default=0.0):
    for k in keys:
        if k in item:
            return to_float(item.get(k), default)
    return default

def scan_full_market_universe(force=False):
    """토스 전체시장 랭킹 후보를 실시간 가격으로 보강해 3그룹 순위를 만든다."""
    state = S.setdefault('full_market', {})
    if not ENABLE_FULL_MARKET_SCANNER:
        state['status'] = '전체시장 스캐너 OFF'
        return False
    if not force and time.time() - to_float(state.get('last_scan_ts', 0)) < FULL_MARKET_SCAN_INTERVAL_SEC:
        return bool(state.get('ranked'))
    universe = load_full_market_universe(force)
    symbols = list(universe)
    state['last_scan_ts'] = time.time()
    state['last_scan_text'] = now_text()
    if not symbols:
        state['status'] = 'FULL_MARKET_UNIVERSE_EMPTY'
        return False
    quote_map = {}
    for i in range(0, len(symbols), 200):
        batch = symbols[i:i + 200]
        code, data = api_get('/api/v1/prices', params={'symbols': ','.join(batch)}, timeout=15)
        if code != 200:
            state['errors'] = int(state.get('errors', 0)) + 1
            continue
        for item in first_list(data):
            if not isinstance(item, dict):
                continue
            sym = str(item.get('symbol') or '').strip()
            if sym:
                quote_map[sym] = item
    for sym, base in universe.items():
        item = quote_map.get(sym, {})
        price = _quote_field(item, ['lastPrice', 'price', 'currentPrice', 'closePrice', 'tradePrice'], to_float(base.get('price'), 0))
        if price < FULL_MARKET_MIN_PRICE:
            continue
        ts = str(item.get('timestamp') or base.get('timestamp') or '')
        api_dt = parse_api_datetime(ts)
        if ENABLE_MARKET_SAFETY_GATE and api_dt and (api_dt.strftime('%Y-%m-%d') != today()):
            continue
        prev = state.setdefault('quotes', {}).get(sym, {})
        prev_price = to_float(prev.get('price'), price)
        short_mom = pct(price, prev_price) if prev_price else 0.0
        q = {**base, 'price': price, 'short_mom': short_mom, 'timestamp': ts, 'saved_at': now_text()}
        state['quotes'][sym] = q
        S.setdefault('prices', {})[sym] = price
        S.setdefault('market_data_capture', {}).setdefault('price_timestamp', {})[sym] = ts
        hist = S.setdefault('history', {}).setdefault(sym, [])
        hist.append(price)
        if len(hist) > TARGET_PATTERN_LOOKBACK_POINTS:
            del hist[:-TARGET_PATTERN_LOOKBACK_POINTS]
        S.setdefault('high', {})[sym] = max(to_float(S.get('high', {}).get(sym, price)), price)
        old_low = to_float(S.get('low', {}).get(sym, price)) or price
        S.setdefault('low', {})[sym] = min(old_low, price)
    ranked = []
    for sym, q in state.get('quotes', {}).items():
        if sym not in universe or sym in FULL_MARKET_BLOCKED_SYMBOLS:
            continue
        if data_age_seconds(q.get('timestamp')) > max(MAX_PRICE_AGE_SEC, FULL_MARKET_SCAN_INTERVAL_SEC * 3):
            continue
        turnover = to_float(q.get('turnover'), 0)
        volume = to_float(q.get('volume'), 0)
        change_pct = to_float(q.get('change_pct'), 0)
        short_mom = to_float(q.get('short_mom'), 0)
        ranks = q.get('ranking_best') if isinstance(q.get('ranking_best'), dict) else {}
        amount_rank = int(ranks.get('MARKET_TRADING_AMOUNT', 9999))
        volume_rank = int(ranks.get('MARKET_TRADING_VOLUME', 9999))
        gainer_rank = int(ranks.get('TOP_GAINERS', 9999))
        loser_rank = int(ranks.get('TOP_LOSERS', 9999))
        rank_bonus = 0.0
        for r, weight in [(amount_rank, 28.0), (volume_rank, 18.0), (gainer_rank, 16.0), (loser_rank, 8.0)]:
            if r <= 100:
                rank_bonus += weight * (101 - r) / 100.0
        score = rank_bonus + min(28.0, max(-28.0, change_pct * 2.2)) + min(20.0, max(-20.0, short_mom * 16.0)) + min(18.0, max(0.0, turnover) ** 0.5 / 24000.0) + min(6.0, max(0.0, volume) ** 0.5 / 2500.0)
        ranked.append((score, sym, q))
    ranked.sort(key=lambda x: x[0], reverse=True)
    state['ranked'] = ranked[:FULL_MARKET_TOP_N]
    state['status'] = f"토스 랭킹시장 후보 {len(universe):,}개, 실시간가격 {len(quote_map):,}개, 최종 {len(state['ranked'])}개"
    return bool(state['ranked'])

def ensure_live_orderbook(sym):
    """3그룹이 선택한 종목의 호가를 주문 직전에 즉시 조회한다."""
    state = S.setdefault('market_data_capture', {})
    ob = state.setdefault('latest_orderbook', {}).get(sym, {})
    if data_age_seconds(ob.get('timestamp')) <= MAX_ORDERBOOK_AGE_SEC and to_float(ob.get('best_ask', 0)) > 0:
        return True
    code, data = api_get('/api/v1/orderbook', params={'symbol': sym}, timeout=8)
    if code != 200:
        return False
    result = _result_dict(data)
    asks = result.get('asks', []) if isinstance(result, dict) and isinstance(result.get('asks', []), list) else []
    bids = result.get('bids', []) if isinstance(result, dict) and isinstance(result.get('bids', []), list) else []
    ts = str(result.get('timestamp', '')) if isinstance(result, dict) else ''
    state['latest_orderbook'][sym] = {'timestamp': ts, 'best_ask': to_float(asks[0].get('price', 0)) if asks else 0, 'best_bid': to_float(bids[0].get('price', 0)) if bids else 0, 'asks': asks, 'bids': bids}
    return bool(asks and bids)

def full_market_candidate(ai_id):
    """G01~G05가 서로 다른 방식으로 전체시장 후보를 고른다."""
    scan_full_market_universe(False)
    ranked = list(S.setdefault('full_market', {}).get('ranked', []))
    scored = []
    for base_score, sym, q in ranked:
        hist = list(S.get('history', {}).get(sym, []) or [])
        cur = to_float(q.get('price', 0))
        if cur <= 0:
            continue

        def move(n):
            return pct(cur, to_float(hist[-n - 1])) if len(hist) > n and to_float(hist[-n - 1]) > 0 else 0.0
        r3, r10 = (move(3), move(10))
        high = max([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [cur])
        low = min([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [cur])
        from_high, from_low = (pct(cur, high), pct(cur, low))
        turnover = to_float(q.get('turnover', 0))
        liquidity = min(30.0, max(turnover, 0.0) ** 0.5 / 20000.0)
        if ai_id == 'G01':
            metric = base_score + liquidity + r3 * 8
        elif ai_id == 'G02':
            metric = liquidity + r3 * 16 + r10 * 8 + (12 if from_high >= -0.3 else -10)
        elif ai_id == 'G03':
            metric = liquidity + from_low * 7 + r3 * 10 if -4.0 <= from_high <= -0.3 and r3 > 0 else -999
        elif ai_id == 'G04':
            metric = liquidity + from_low * 9 + r3 * 14 if from_low >= 1.0 and r10 < 0 else -999
        else:
            metric = base_score * 0.45 + liquidity + r3 * 10 + r10 * 6 - abs(from_high) * 1.5
        scored.append((metric, sym, base_score, r3, r10, from_high, from_low, liquidity))
    return max(scored, default=(0, '', 0, 0, 0, 0, 0, 0), key=lambda x: x[0])

def multi_ai_path(ai_id):
    return os.path.join(day_dir(), f'paper_ai_{ai_id}_{today()}.csv')

def _multi_ai_default(ai_id):
    return {'id': ai_id, 'name': MULTI_AI_NAMES.get(ai_id, ai_id), 'start_cash': MULTI_AI_START_CASH, 'cash': MULTI_AI_START_CASH, 'positions': {}, 'realized_pl': 0, 'asset': MULTI_AI_START_CASH, 'profit_rate': 0.0, 'trades': [], 'last_action': '초기화', 'last_decision_ts': 0, 'last_decision_date': '', 'group': MULTI_AI_GROUP.get(ai_id, ''), 'universe_type': MULTI_AI_UNIVERSE.get(ai_id, ''), 'parent_strategy': MULTI_AI_PARENT.get(ai_id, ai_id), 'mdd_pct': 0.0, 'peak_asset': MULTI_AI_START_CASH, 'loss_streak': 0, 'decision_data_end': '', 'combo_date': '', 'combo_phase': 0, 'combo_last_symbol': '', 'daily_assets': {}, 'selected_source': '', 'selected_sources': [], 'selection_date': '', 'selection_reason': ''}

def ensure_multi_ai_states():
    with LOCK:
        states = S.setdefault('paper_ais', {})
        for ai_id in MULTI_AI_IDS:
            cur = states.get(ai_id)
            if not isinstance(cur, dict):
                states[ai_id] = _multi_ai_default(ai_id)
                continue
            default = _multi_ai_default(ai_id)
            for k, v in default.items():
                cur.setdefault(k, v)
            cur['id'] = ai_id
            cur['name'] = MULTI_AI_NAMES.get(ai_id, ai_id)
            cur.setdefault('positions', {})
            cur.setdefault('trades', [])

def _multi_ai_asset(ai_id):
    ensure_multi_ai_states()
    with LOCK:
        st = S['paper_ais'][ai_id]
        total = to_float(st.get('cash', 0))
        positions = dict(st.get('positions', {}))
        prices = dict(S.get('prices', {}))
    for sym, pos in positions.items():
        total += to_float(pos.get('qty', 0)) * prices.get(sym, to_float(pos.get('avg', 0)))
    return int(total)

def _multi_ai_update(ai_id):
    asset = _multi_ai_asset(ai_id)
    with LOCK:
        st = S['paper_ais'][ai_id]
        st['asset'] = asset
        st['profit_rate'] = pct(asset, st.get('start_cash', MULTI_AI_START_CASH))
        peak = max(to_float(st.get('peak_asset', MULTI_AI_START_CASH)), asset)
        st['peak_asset'] = peak
        st['mdd_pct'] = min(to_float(st.get('mdd_pct', 0)), pct(asset, peak) if peak else 0)

def _multi_ai_record(ai_id, action, sym, price, qty, fee, pl, reason, partial=False):
    _multi_ai_update(ai_id)
    with LOCK:
        st = S['paper_ais'][ai_id]
        row = {'time': now_text(), 'ai_id': ai_id, 'ai_name': st.get('name', ai_id), 'action': action, 'symbol': sym, 'name': name_of(sym), 'price': round(to_float(price), 4), 'qty': int(qty), 'fee': int(fee), 'pl': int(pl), 'cash': int(to_float(st.get('cash', 0))), 'asset': int(to_float(st.get('asset', 0))), 'profit_rate': round(to_float(st.get('profit_rate', 0)), 4), 'reason': reason, 'partial': bool(partial), 'real_order': False}
        st.setdefault('trades', []).insert(0, row)
        st['trades'] = st['trades'][:200]
        st['last_action'] = f'{now_short()} {action} {name_of(sym)}'
    write_row(multi_ai_path(ai_id), ['time', 'ai_id', 'ai_name', 'action', 'symbol', 'name', 'price', 'qty', 'fee', 'pl', 'cash', 'asset', 'profit_rate', 'reason', 'partial', 'real_order'], row)
    save_state()

def _multi_ai_buy(ai_id, sym, reason, ratio=None):
    if not ensure_live_orderbook(sym):
        return False
    gate_ok, gate_reason = market_safety_gate(sym)
    if not gate_ok:
        return False
    ensure_multi_ai_states()
    with LOCK:
        st = S['paper_ais'][ai_id]
        if st.get('positions'):
            return False
        cash = int(to_float(st.get('cash', 0)))
    use_ratio = MULTI_AI_MAX_POSITION_RATIO if ratio is None else min(MULTI_AI_MAX_POSITION_RATIO, max(0.05, ratio))
    budget = int(cash * use_ratio)
    fee_rate = MULTI_AI_FEE_SIDE_PCT / 100
    fill = simulated_orderbook_fill(sym, 'BUY', max_cash=budget / (1 + fee_rate))
    if not fill.get('ok'):
        return False
    qty = int(fill.get('qty', 0))
    price = to_float(fill.get('avg_price', 0))
    gross = int(round(fill.get('gross', 0)))
    fee = int(round(gross * fee_rate))
    total = gross + fee
    while qty > 0 and total > cash:
        qty -= 1
        gross = int(round(qty * price))
        fee = int(round(gross * fee_rate))
        total = gross + fee
    if qty <= 0:
        return False
    with LOCK:
        st = S['paper_ais'][ai_id]
        st['cash'] = cash - total
        st['positions'][sym] = {'qty': qty, 'avg': price, 'entry_time': now_text(), 'entry_date': today(), 'entry_total_cost': total, 'entry_fee': fee, 'high_after_buy': price}
    _multi_ai_record(ai_id, '가상매수', sym, price, qty, fee, 0, reason, bool(fill.get('partial')))
    return True

def _multi_ai_sell(ai_id, sym, reason):
    ensure_multi_ai_states()
    with LOCK:
        st = S['paper_ais'][ai_id]
        pos = st.get('positions', {}).get(sym)
        if not isinstance(pos, dict):
            return False
        qty = int(to_float(pos.get('qty', 0)))
        avg = to_float(pos.get('avg', 0))
        total_cost = int(to_float(pos.get('entry_total_cost', qty * avg)))
    gate_ok, _ = market_safety_gate(sym)
    if not gate_ok:
        return False
    fill = simulated_orderbook_fill(sym, 'SELL', qty=qty)
    if not fill.get('ok'):
        return False
    sold = int(fill.get('qty', 0))
    price = to_float(fill.get('avg_price', 0))
    gross = int(round(fill.get('gross', 0)))
    fee = int(round(gross * MULTI_AI_FEE_SIDE_PCT / 100))
    net = gross - fee
    cost_part = int(round(total_cost * sold / max(1, qty)))
    pl = net - cost_part
    remain = qty - sold
    with LOCK:
        st = S['paper_ais'][ai_id]
        st['cash'] = int(to_float(st.get('cash', 0))) + net
        st['realized_pl'] = int(to_float(st.get('realized_pl', 0))) + pl
        if remain <= 0:
            st['positions'].pop(sym, None)
        else:
            pos['qty'] = remain
            pos['entry_total_cost'] = max(0, total_cost - cost_part)
            st['positions'][sym] = pos
    _multi_ai_record(ai_id, '가상매도', sym, price, sold, fee, pl, reason, remain > 0)
    return True

def _multi_ai_recent_metrics(sym):
    with LOCK:
        hist = list(S.get('history', {}).get(sym, []) or [])
        signals = dict(S.get('signals', {}))
    sig = signals.get(sym, {}) if isinstance(signals.get(sym), dict) else {}
    score = to_float(sig.get('score', 0))

    def move(points):
        if len(hist) >= points + 1 and to_float(hist[-points - 1]) > 0:
            return pct(to_float(hist[-1]), to_float(hist[-points - 1]))
        return 0.0
    r3 = move(3)
    r10 = move(10)
    high = max([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [0])
    low = min([to_float(x) for x in hist[-30:] if to_float(x) > 0] or [0])
    cur = to_float(hist[-1]) if hist else 0
    from_high = pct(cur, high) if high else 0
    from_low = pct(cur, low) if low else 0
    return (score, r3, r10, from_high, from_low)

def _learning_base_ids():
    """학습 계좌가 비교할 실시간 가상계좌. 조합·학습계좌 자신은 제외한다."""
    return [x for x in MULTI_AI_IDS if x.startswith(('RI', 'RE', 'WI', 'WE', 'G'))]

def _record_multi_ai_daily_assets():
    """매 루프 현재 자산을 오늘 날짜 스냅숏으로 저장한다. 다음날 선택에는 전일까지 값만 쓴다."""
    d = today()
    with LOCK:
        for ai_id in MULTI_AI_IDS:
            st = S.get('paper_ais', {}).get(ai_id, {})
            st.setdefault('daily_assets', {})[d] = int(to_float(st.get('asset', st.get('cash', 0))))
            keys = sorted(st.get('daily_assets', {}))
            for old in keys[:-40]:
                st['daily_assets'].pop(old, None)

def _source_daily_returns(source_id, window=5, extra_cost_pct=0.0):
    st = S.get('paper_ais', {}).get(source_id, {})
    assets = st.get('daily_assets', {}) if isinstance(st.get('daily_assets'), dict) else {}
    ds = sorted([d for d in assets if d < today()])
    vals = []
    for d0, d1 in zip(ds[:-1], ds[1:]):
        a0 = to_float(assets.get(d0, 0))
        a1 = to_float(assets.get(d1, 0))
        if a0 > 0 and a1 > 0:
            vals.append((d1, a1 / a0 - 1.0 - extra_cost_pct / 100.0))
    return vals[-window:]

def _learning_score(source_id, ai_id):
    window = 7 if ai_id == 'L03' else 5
    extra_cost = 0.1 if ai_id == 'L05' else 0.0
    vals = _source_daily_returns(source_id, window, extra_cost)
    if len(vals) < 2:
        return -9999.0
    rs = [r for _, r in vals]
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rs:
        equity *= 1 + r
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
    total = equity - 1
    if ai_id in ['L01', 'L02']:
        w = [0.5 + i * (1.0 / max(1, len(rs) - 1)) for i in range(len(rs))]
        return sum((r * x for r, x in zip(rs, w))) / sum(w) + 0.5 * mdd
    if ai_id == 'L03':
        return total
    if ai_id == 'L04':
        return total + 2.5 * mdd
    return total + 4.0 * mdd - max(0, -min(rs)) * 1.5

def _select_learning_sources(ai_id, force=False):
    with LOCK:
        st = S['paper_ais'][ai_id]
        if not force and st.get('selection_date') == today():
            return list(st.get('selected_sources', []) or [])
    scored = []
    for src in _learning_base_ids():
        sc = _learning_score(src, ai_id)
        if sc > -9990:
            scored.append((sc, src))
    scored.sort(reverse=True)
    topn = 3 if ai_id == 'L02' else 1
    chosen = [src for _, src in scored[:topn]]
    with LOCK:
        st = S['paper_ais'][ai_id]
        st['selection_date'] = today()
        st['selected_sources'] = chosen
        st['selected_source'] = chosen[0] if chosen else ''
        st['selection_reason'] = f'전일까지 최근성과 선택: ' + ', '.join((f'{src}={sc:.4f}' for sc, src in scored[:topn])) if chosen else '학습자료 부족'
        st['last_action'] = f'{now_short()} 학습선택 ' + (','.join(chosen) if chosen else '자료부족 관망')
    return chosen

def _learning_effective_source(ai_id):
    chosen = _select_learning_sources(ai_id, False)
    return chosen[0] if chosen else ''

def _multi_ai_parent_id(ai_id):
    if str(ai_id).startswith('L'):
        src = _learning_effective_source(ai_id)
        return MULTI_AI_PARENT.get(src, src) if src else ai_id
    return MULTI_AI_PARENT.get(ai_id, ai_id)

def _multi_ai_index(ai_id):
    parent = _multi_ai_parent_id(ai_id)
    digits = ''.join((ch for ch in parent if ch.isdigit()))
    return int(digits) if digits else 1

def _multi_ai_family(ai_id):
    parent = _multi_ai_parent_id(ai_id)
    return parent[:1] if parent else ''

def _multi_ai_universe_lists(ai_id, mode):
    if str(ai_id).startswith('L'):
        src = _learning_effective_source(ai_id)
        if src:
            ai_id = src
    etf_long = ['122630', '233740', '069500', '229200', '494310', '488080', '469150']
    etf_inv = ['252670', '251340']
    samsung_hynix_long = ['0193T0', '000660', '0193W0', '005930']
    samsung_hynix_inv = ['0197X0', '0193L0']
    include_family = MULTI_AI_UNIVERSE.get(ai_id) == 'INCLUDE_SAMSUNG_HYNIX'
    if mode == 'DOWN':
        return etf_inv + (samsung_hynix_inv if include_family else [])
    return etf_long + (samsung_hynix_long if include_family else [])

def _multi_ai_candidate(ai_id, mode):
    """그룹별 후보 선택. 학습형은 전일까지 선택한 원본 전략 규칙을 당일 고정 적용한다."""
    if ai_id.startswith('L'):
        chosen = _select_learning_sources(ai_id, False)
        if not chosen:
            return (0, '', 0, 0, 0, 0, 0, 0)
        results = [_multi_ai_candidate(src, mode) for src in chosen]
        return max(results, default=(0, '', 0, 0, 0, 0, 0, 0), key=lambda x: x[0])
    if ai_id.startswith('G'):
        return full_market_candidate(ai_id)
    with LOCK:
        prices = dict(S.get('prices', {}))
    universe = _multi_ai_universe_lists(ai_id, mode)
    market_ref = '252670' if mode == 'DOWN' else '069500'
    _, _, market_r10, _, _ = _multi_ai_recent_metrics(market_ref)
    scored = []
    idx = _multi_ai_index(ai_id)
    family = _multi_ai_family(ai_id)
    parent = _multi_ai_parent_id(ai_id)
    for sym in universe:
        if prices.get(sym, 0) <= 0:
            continue
        score, r3, r10, from_high, from_low = _multi_ai_recent_metrics(sym)
        rel = r10 - market_r10
        if family == 'R':
            methods = idx % 5
            if methods == 1:
                metric = score * 0.4 + r10 * 8 + rel * 4
            elif methods == 2:
                metric = score * 0.3 - r3 * 8 + from_low * 4
            elif methods == 3:
                metric = score * 0.25 + r3 * 14 + (10 if from_high >= -0.25 else -15)
            elif methods == 4:
                metric = score * 0.3 + from_low * 6 + r3 * 8 if -3.5 <= from_high <= -0.3 else -999
            else:
                metric = score * 0.55 + rel * 5 - abs(r3) * 2
        else:
            st = S.get('paper_ais', {}).get(ai_id, {})
            own_penalty = max(0.0, -to_float(st.get('profit_rate', 0))) * 0.25
            look = [3, 5, 7, 10][(idx - 1) % 4]
            momentum = r3 if look <= 3 else r10
            if parent == 'W13':
                momentum = -r3
            if parent == 'W15' and mode in ['CHOPPY', 'NO_TRADE', 'RECOVERY']:
                metric = -999
            else:
                metric = score * 0.35 + momentum * 10 + rel * 5 + from_low * 2 - own_penalty
        scored.append((metric, sym, score, r3, r10, from_high, from_low, rel))
    return max(scored, default=(0, '', 0, 0, 0, 0, 0, 0), key=lambda x: x[0])

def _multi_ai_entry_window(ai_id, hhmm):
    if str(ai_id).startswith('L'):
        src = _learning_effective_source(ai_id)
        return _multi_ai_entry_window(src, hhmm) if src else False
    family = _multi_ai_family(ai_id)
    idx = _multi_ai_index(ai_id)
    if family == 'G':
        return '09:10' <= hhmm < '14:40'
    if family == 'R':
        fixed = {5: '09:15', 6: '10:00', 7: '11:00', 8: '12:30', 9: '13:00', 10: '13:30'}
        if idx in fixed:
            t = fixed[idx]
            return t <= hhmm <= f'{t[:3]}{min(59, int(t[3:]) + 3):02d}'
        if idx == 15:
            return '14:45' <= hhmm <= '15:05'
    return '09:15' <= hhmm < '14:30'

def _multi_ai_exit_reason(ai_id, sym, pos, mode, hhmm):
    logic_id = _learning_effective_source(ai_id) if str(ai_id).startswith('L') else ai_id
    price = to_float(S.get('prices', {}).get(sym, 0))
    avg = to_float(pos.get('avg', 0))
    if price <= 0 or avg <= 0:
        return ''
    high = max(to_float(pos.get('high_after_buy', avg)), price)
    with LOCK:
        if sym in S['paper_ais'][ai_id]['positions']:
            S['paper_ais'][ai_id]['positions'][sym]['high_after_buy'] = high
    profit = pct(price, avg)
    draw = pct(price, high)
    parent = _multi_ai_parent_id(logic_id)
    family = _multi_ai_family(logic_id)
    if family == 'G':
        stops = {'G01': -1.4, 'G02': -1.8, 'G03': -1.3, 'G04': -1.6, 'G05': -1.2}
        trails = {'G01': -0.9, 'G02': -1.1, 'G03': -0.7, 'G04': -0.9, 'G05': -0.8}
        if profit <= stops[parent]:
            return f'{ai_id} 실시간 손실제한 {profit:.2f}%'
        if profit >= 0.7 and draw <= trails[parent]:
            return f'{ai_id} 실시간 수익보호 {draw:.2f}%'
        if hhmm >= '15:10':
            return f'{ai_id} 당일 15:10 청산'
    elif parent == 'R14':
        if profit >= 0.8 and draw <= -1.0:
            return f'{ai_id} 추적청산 {draw:.2f}%'
    else:
        if profit <= -2.0:
            return f'{ai_id} 손실제한 {profit:.2f}%'
        if profit >= 0.8 and draw <= -1.0:
            return f'{ai_id} 수익보호 {draw:.2f}%'
        if parent != 'R15' and hhmm >= '15:10':
            return f'{ai_id} 당일청산'
    return ''

def _combo_reset_daily(ai_id):
    with LOCK:
        st = S['paper_ais'][ai_id]
        if st.get('combo_date') != today():
            st['combo_date'] = today()
            st['combo_phase'] = 0
            st['combo_last_symbol'] = ''
            st['last_decision_ts'] = 0

def _combo_mode_for_phase(ai_id, phase, market_mode):
    if ai_id == 'C01':
        return 'DOWN' if phase == 0 else 'UP'
    if ai_id == 'C02':
        return 'DOWN'
    if ai_id == 'C03':
        return 'DOWN' if phase == 0 else 'UP'
    return 'DOWN' if market_mode == 'DOWN' else 'UP'

def _combo_times(ai_id):
    if ai_id == 'C03':
        return ('09:15', '11:30', '11:31', '14:00')
    return ('09:15', '12:00', '12:01', '15:00')

def _combo_pick_candidate(ai_id, direction):
    metric, sym, score, r3, r10, from_high, from_low, rel = _multi_ai_candidate(ai_id, direction)
    return (metric, sym, score, r3, r10, from_high, from_low, rel)

def _run_combo_account(ai_id, market_mode, hhmm, now_ts):
    _combo_reset_daily(ai_id)
    entry1, exit1, entry2, exit2 = _combo_times(ai_id)
    with LOCK:
        st = S['paper_ais'][ai_id]
        phase = int(to_float(st.get('combo_phase', 0)))
        positions = dict(st.get('positions', {}))
        last_ts = to_float(st.get('last_decision_ts', 0))
    if phase == 1 and positions and (hhmm >= exit1):
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f'{ai_id} 1차 구간 {exit1} 청산'):
                with LOCK:
                    st = S['paper_ais'][ai_id]
                    st['combo_phase'] = 2
                    st['last_decision_ts'] = 0
        return True
    if phase == 3 and positions and (hhmm >= exit2):
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f'{ai_id} 2차 구간 {exit2} 청산'):
                with LOCK:
                    st = S['paper_ais'][ai_id]
                    st['combo_phase'] = 4
                    st['last_decision_ts'] = now_ts
        return True
    if positions:
        return True
    if now_ts - last_ts < MULTI_AI_DECISION_COOLDOWN_SEC:
        return True
    if phase == 0 and entry1 <= hhmm < exit1:
        direction = _combo_mode_for_phase(ai_id, 0, market_mode)
        metric, sym, score, r3, r10, from_high, from_low, rel = _combo_pick_candidate(ai_id, direction)
        if sym and metric >= 35:
            reason = f'{MULTI_AI_NAMES[ai_id]} 1차 direction={direction}, metric={metric:.1f}, score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, rel={rel:.2f}%, decision_data_end={now_text()}'
            if _multi_ai_buy(ai_id, sym, reason, 0.7):
                with LOCK:
                    st = S['paper_ais'][ai_id]
                    st['combo_phase'] = 1
                    st['combo_last_symbol'] = sym
                    st['last_decision_ts'] = now_ts
                return True
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['combo_phase'] = 2
            st['last_decision_ts'] = 0
            st['last_action'] = f'{now_short()} 1차 1회평가 관망 metric={metric:.1f}'
        return True
    if phase == 2 and entry2 <= hhmm < exit2:
        direction = _combo_mode_for_phase(ai_id, 1, market_mode)
        metric, sym, score, r3, r10, from_high, from_low, rel = _combo_pick_candidate(ai_id, direction)
        if sym and metric >= 35:
            reason = f'{MULTI_AI_NAMES[ai_id]} 2차 direction={direction}, metric={metric:.1f}, score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, rel={rel:.2f}%, decision_data_end={now_text()}'
            if _multi_ai_buy(ai_id, sym, reason, 0.7):
                with LOCK:
                    st = S['paper_ais'][ai_id]
                    st['combo_phase'] = 3
                    st['combo_last_symbol'] = sym
                    st['last_decision_ts'] = now_ts
                return True
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['combo_phase'] = 4
            st['last_decision_ts'] = now_ts
            st['last_action'] = f'{now_short()} 2차 1회평가 관망 metric={metric:.1f}'
        return True
    return True

def _verified_candle_rows(sym):
    """오늘 저장된 1분봉을 timestamp 기준으로 중복 제거하여 시간순 반환한다."""
    path = candle_1m_path(sym)
    if not os.path.exists(path):
        return []
    by_ts = {}
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                ts = str(row.get('timestamp', ''))
                dt = parse_api_datetime(ts)
                close = to_float(row.get('close', 0))
                if dt and close > 0 and (dt.strftime('%Y-%m-%d') == today()):
                    by_ts[dt] = close
    except Exception as e:
        set_error(f'검증전략 1분봉 읽기 실패 {sym}: {e}')
        return []
    return sorted(by_ts.items(), key=lambda x: x[0])

def _verified_ret(sym, minutes, end_hhmm):
    rows = _verified_candle_rows(sym)
    if not rows:
        return 0.0
    h, m = [int(x) for x in end_hhmm.split(':')]
    end_dt = now_kst().replace(hour=h, minute=m, second=59, microsecond=999999)
    start_dt = end_dt - __import__('datetime').timedelta(minutes=int(minutes))
    end_vals = [(dt, px) for dt, px in rows if dt <= end_dt]
    start_vals = [(dt, px) for dt, px in rows if dt <= start_dt]
    if not end_vals or not start_vals:
        return 0.0
    return pct(end_vals[-1][1], start_vals[-1][1])

def _verified_open_ret(sym, end_hhmm):
    rows = _verified_candle_rows(sym)
    if not rows:
        return 0.0
    h, m = [int(x) for x in end_hhmm.split(':')]
    end_dt = now_kst().replace(hour=h, minute=m, second=59, microsecond=999999)
    vals = [(dt, px) for dt, px in rows if dt <= end_dt]
    if not vals:
        return 0.0
    return pct(vals[-1][1], vals[0][1])

def _verified_rule_pick(ai_id, turn):
    """사용자가 제공한 확정 규칙 파일을 코드로 그대로 옮긴 선택 함수."""
    end = '09:45' if turn == 1 else '12:30'
    if ai_id == 'V01':
        if turn == 1:
            h = _verified_ret('000660', 45, end)
            s = _verified_ret('005930', 45, end)
            a = _verified_ret('494310', 45, end)
            b = _verified_ret('252670', 45, end)
            spread = a - b
            if h <= -2.92:
                pick = '252670' if s > -1.99 or spread <= -7.3 else '494310'
            else:
                pick = '494310' if a <= 10.09 else '252670'
            return (pick, f'V01-1 h45={h:.2f} s45={s:.2f} spread={spread:.2f}')
        a = _verified_ret('494310', 5, end)
        inv = _verified_ret('0193L0', 5, end)
        pair = _verified_ret('0193T0', 5, end) - _verified_ret('0197X0', 5, end)
        if a <= 0.51 and inv <= -0.34:
            return ('494310', f'V01-2 a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
        if a <= 0.51 and pair <= -0.58:
            return ('252670', f'V01-2 a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
        return ('', f'V01-2 SKIP a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
    if ai_id == 'V02':
        if turn == 1:
            lev = _verified_ret('0193T0', 45, end)
            inv2 = _verified_ret('252670', 45, end)
            underlying = _verified_ret('000660', 45, end) - _verified_ret('005930', 45, end)
            pick = '494310' if lev > -7.66 and inv2 > -8.3 and (underlying > -1.73) else '252670'
            return (pick, f'V02-1 lev45={lev:.2f} inv45={inv2:.2f} underlying={underlying:.2f}')
        a = _verified_ret('494310', 5, end)
        inv = _verified_ret('0193L0', 5, end)
        pair = _verified_ret('0193T0', 5, end) - _verified_ret('0197X0', 5, end)
        if a <= 0.51 and inv <= -0.34:
            return ('494310', f'V02-2 a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
        if a <= 0.51 and pair <= -0.58:
            return ('252670', f'V02-2 a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
        return ('', f'V02-2 SKIP a5={a:.2f} inv5={inv:.2f} pair={pair:.2f}')
    if ai_id == 'V03':
        if turn == 1:
            h45 = _verified_ret('000660', 45, end)
            inv5 = _verified_ret('252670', 5, end)
            u30 = _verified_ret('000660', 30, end) - _verified_ret('005930', 30, end)
            t30 = _verified_ret('494310', 30, end) - _verified_ret('252670', 30, end)
            op = _verified_open_ret('494310', end) - _verified_open_ret('252670', end)
            h15 = _verified_ret('000660', 15, end)
            if h45 <= -3.0:
                if inv5 <= 1.0:
                    if u30 <= 0.0:
                        pick = '0193T0' if t30 <= -5.0 else '0193W0'
                    else:
                        pick = '0193L0'
                else:
                    pick = '0193T0'
            elif op <= 14.0:
                pick = '0197X0'
            else:
                pick = '0193W0' if h15 <= 0.0 else '0193L0'
            return (pick, f'V03-1 h45={h45:.2f} inv5={inv5:.2f} u30={u30:.2f} t30={t30:.2f} open={op:.2f} h15={h15:.2f}')
        a5 = _verified_ret('494310', 5, end)
        w15 = _verified_ret('0193W0', 15, end)
        a10 = _verified_ret('494310', 10, end)
        l15 = _verified_ret('0193L0', 15, end)
        pair60 = _verified_ret('0193T0', 60, end) - _verified_ret('0193L0', 60, end)
        x90 = _verified_ret('0197X0', 90, end)
        if a5 <= 1.0:
            if w15 <= 1.0:
                if a10 <= -1.0:
                    if l15 <= 0.0:
                        pick = '0193L0'
                    else:
                        pick = '0193T0' if pair60 <= 1.0 else ''
                else:
                    pick = '0193T0' if x90 <= -4.0 else '0193W0'
            else:
                pick = '0197X0'
        else:
            pick = '0193T0'
        return (pick, f'V03-2 a5={a5:.2f} w15={w15:.2f} a10={a10:.2f} l15={l15:.2f} pair60={pair60:.2f} x90={x90:.2f}')
    return ('', 'UNKNOWN_VERIFIED_RULE')

def _run_verified_fixed_account(ai_id, hhmm, now_ts):
    _combo_reset_daily(ai_id)
    with LOCK:
        st = S['paper_ais'][ai_id]
        phase = int(to_float(st.get('combo_phase', 0)))
        positions = dict(st.get('positions', {}))
    if phase == 1 and positions and (hhmm >= '12:00'):
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f'{ai_id} 1차 12:00 고정청산'):
                with LOCK:
                    S['paper_ais'][ai_id]['combo_phase'] = 2
        return True
    if phase == 3 and positions and (hhmm >= '15:20'):
        for sym in list(positions):
            ensure_live_orderbook(sym)
            if _multi_ai_sell(ai_id, sym, f'{ai_id} 2차 15:20 고정청산'):
                with LOCK:
                    S['paper_ais'][ai_id]['combo_phase'] = 4
        return True
    if positions:
        return True
    if phase == 0 and '09:45' <= hhmm < '09:50':
        sym, reason = _verified_rule_pick(ai_id, 1)
        ok = bool(sym) and _multi_ai_buy(ai_id, sym, reason + f' decision_data_end={now_text()}', 0.9)
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['combo_phase'] = 1 if ok else 2
            st['last_decision_ts'] = now_ts
            if not ok:
                st['last_action'] = f'{now_short()} 1차 관망 {reason}'
        return True
    if phase == 2 and '12:30' <= hhmm < '12:35':
        sym, reason = _verified_rule_pick(ai_id, 2)
        ok = bool(sym) and _multi_ai_buy(ai_id, sym, reason + f' decision_data_end={now_text()}', 0.9)
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['combo_phase'] = 3 if ok else 4
            st['last_decision_ts'] = now_ts
            if not ok:
                st['last_action'] = f'{now_short()} 2차 관망 {reason}'
        return True
    return True

def _csv_daily_closes(sym, limit=30):
    path = os.path.join(market_data_dir(), f'candles_1d_{sym}.csv')
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                d = str(row.get('date') or row.get('time') or row.get('timestamp') or row.get('dt') or '')
                c = to_float(row.get('close') or row.get('closingPrice') or row.get('price') or row.get('close_price'), 0)
                if c > 0:
                    out.append((d, c))
    except Exception as e:
        set_error(f'daily close read {sym}: {e}')
    return out[-limit:]

def _daily_consensus_signal():
    votes = []
    detail = []
    for sym in ['005930', '000660', '069500']:
        vals = _csv_daily_closes(sym, 20)
        if len(vals) < 11:
            return (0, f'DAILY_NOT_READY {sym} rows={len(vals)}')
        closes = [x[1] for x in vals]
        last, prev = (closes[-1], closes[-2])
        ma10 = sum(closes[-10:]) / 10
        vote = 1 if last > prev and last > ma10 else -1 if last < prev and last < ma10 else 0
        votes.append(vote)
        detail.append(f'{sym}:{vote}')
    sig = 1 if votes == [1, 1, 1] else -1 if votes == [-1, -1, -1] else 0
    return (sig, ' '.join(detail))

def _intraday_direction(end_hhmm='09:30', minutes=15):
    rs = {s: _verified_ret(s, minutes, end_hhmm) for s in ['005930', '000660', '069500']}
    up = sum((1 for v in rs.values() if v > 0.05))
    down = sum((1 for v in rs.values() if v < -0.05))
    sig = 1 if up >= 2 else -1 if down >= 2 else 0
    return (sig, rs)

def _same_direction_pick(direction, end_hhmm, minutes=15, allow_single=True):
    if direction > 0:
        cands = ['0193T0', '0193W0', '494310', '122630', '233740']
        ranked = sorted(((_verified_ret(s, minutes, end_hhmm), s) for s in cands), reverse=True)
    elif direction < 0:
        cands = ['0197X0', '0193L0', '252670', '251340']
        ranked = sorted(((_verified_ret(s, minutes, end_hhmm), s) for s in cands), reverse=True)
    else:
        return ('', 'NO_DIRECTION')
    best_ret, best_sym = ranked[0]
    if not allow_single and best_ret <= 0:
        return ('', f'NO_POSITIVE_STRENGTH best={best_ret:.2f}')
    return (best_sym, f'direction={direction} strength={best_ret:.2f}')

def _data_trade_filter(end_hhmm):
    for sym in ['005930', '000660', '069500', '494310', '252670']:
        if to_float(S.get('prices', {}).get(sym, 0)) <= 0:
            return (False, f'MISSING_PRICE {sym}')
    h = _verified_ret('000660', 10, end_hhmm)
    s = _verified_ret('005930', 10, end_hhmm)
    if h * s < 0 and abs(h - s) > 0.5:
        return (False, f'MIXED_UNDERLYING h={h:.2f} s={s:.2f}')
    return (True, f'FILTER_OK h={h:.2f} s={s:.2f}')
EXPANDED_SCHEDULES = {'V04': [('09:05', '15:10')], 'V05': [('09:25', '12:00'), ('12:35', '15:10')], 'V06': [('09:30', '12:00'), ('12:30', '15:10')], 'V07': [('09:30', '12:00'), ('12:30', '15:10')], 'V08': [('09:30', '12:00'), ('12:30', '15:10')], 'V09': [('09:15', '10:15')], 'V10': [('10:00', '11:30')], 'V11': [('11:00', '12:30')], 'V12': [('11:00', '12:30')], 'V14': [('09:20', '10:20'), ('10:30', '11:30'), ('12:30', '13:30'), ('14:00', '15:10')], 'V15': [('09:30', '11:30'), ('12:30', '15:10')]}

def _expanded_pick(ai_id, slot, entry_hhmm):
    daily_sig, daily_reason = _daily_consensus_signal()
    intraday_sig, rs = _intraday_direction(entry_hhmm, 15 if entry_hhmm < '11:00' else 30)
    ok_filter, filter_reason = _data_trade_filter(entry_hhmm)
    if ai_id == 'V04':
        sym, why = _same_direction_pick(daily_sig, entry_hhmm, 15, False)
        return (sym, f'V04 {daily_reason} {why}')
    if ai_id == 'V05':
        if daily_sig == 0:
            return ('', f'V05 DAILY_NO_TRADE {daily_reason}')
        h20 = _verified_ret('000660', 20, entry_hhmm)
        h5 = _verified_ret('000660', 5, entry_hhmm)
        s20 = _verified_ret('005930', 20, entry_hhmm)
        s5 = _verified_ret('005930', 5, entry_hhmm)
        reentry = h20 * daily_sig > 0 and h5 * daily_sig > 0 and (s20 * daily_sig > 0) and (s5 * daily_sig > 0)
        if not reentry:
            return ('', f'V05 NO_REENTRY h20={h20:.2f} h5={h5:.2f} s20={s20:.2f} s5={s5:.2f}')
        sym, why = _same_direction_pick(daily_sig, entry_hhmm, 10, False)
        return (sym, f'V05 {daily_reason} {why}')
    if ai_id == 'V06':
        direction = daily_sig or intraday_sig
        sym, why = _same_direction_pick(direction, entry_hhmm, 30, False)
        return (sym, f'V06 daily={daily_sig} intra={intraday_sig} {why}')
    if ai_id == 'V07':
        h = _verified_ret('000660', 15, entry_hhmm)
        s = _verified_ret('005930', 15, entry_hhmm)
        direction = 1 if h > 0.05 and s > 0.05 else -1 if h < -0.05 and s < -0.05 else 0
        sym, why = _same_direction_pick(direction, entry_hhmm, 15, False)
        return (sym, f'V07 h={h:.2f} s={s:.2f} {why}')
    if ai_id == 'V08':
        if not ok_filter:
            return ('', f'V08 {filter_reason}')
        sym, why = _same_direction_pick(intraday_sig, entry_hhmm, 15, False)
        return (sym, f'V08 {filter_reason} {why}')
    if ai_id in ['V09', 'V10', 'V11']:
        sym, why = _same_direction_pick(intraday_sig, entry_hhmm, 15, False)
        return (sym, f'{ai_id} fixed {why} rs={rs}')
    if ai_id == 'V12':
        sym, why = _same_direction_pick(intraday_sig, entry_hhmm, 30, False)
        return (sym, f'V12 consensus90 {why} rs={rs}')
    if ai_id == 'V14':
        sym, why = _same_direction_pick(intraday_sig, entry_hhmm, 10, False)
        return (sym, f'V14 slot={slot + 1} {why}')
    if ai_id == 'V15':
        sym, why = _same_direction_pick(intraday_sig, entry_hhmm, 20, False)
        return (sym, f'V15 slot={slot + 1} direction_switch_or_reentry {why}')
    return ('', 'UNKNOWN_EXPANDED')

def _expanded_reset(ai_id):
    with LOCK:
        st = S['paper_ais'][ai_id]
        if st.get('expanded_date') != today():
            st['expanded_date'] = today()
            st['expanded_slot'] = 0
            st['last_decision_ts'] = 0

def _run_expanded_account(ai_id, hhmm, now_ts):
    if ai_id == 'V13':
        with LOCK:
            st = S['paper_ais'][ai_id]
            positions = dict(st.get('positions', {}))
            last_date = st.get('overnight_entry_date', '')
        if positions and last_date and (last_date != today()) and (hhmm >= '09:05'):
            for sym in list(positions):
                ensure_live_orderbook(sym)
                _multi_ai_sell(ai_id, sym, 'V13 다음 거래일 09:05 오버나이트 청산')
            return True
        if not positions and '15:10' <= hhmm < '15:15':
            sig, rs = _intraday_direction('15:10', 30)
            sym, why = _same_direction_pick(sig, '15:10', 30, False)
            if sym and _multi_ai_buy(ai_id, sym, f'V13 오버나이트 진입 {why} rs={rs}', 0.9):
                with LOCK:
                    S['paper_ais'][ai_id]['overnight_entry_date'] = today()
            return True
        return True
    _expanded_reset(ai_id)
    schedule = EXPANDED_SCHEDULES.get(ai_id, [])
    with LOCK:
        st = S['paper_ais'][ai_id]
        slot = int(to_float(st.get('expanded_slot', 0)))
        positions = dict(st.get('positions', {}))
    if slot >= len(schedule):
        return True
    entry, exit_ = schedule[slot]
    if positions and hhmm >= exit_:
        for sym in list(positions):
            ensure_live_orderbook(sym)
            _multi_ai_sell(ai_id, sym, f'{ai_id} {slot + 1}차 {exit_} 고정청산')
        with LOCK:
            S['paper_ais'][ai_id]['expanded_slot'] = slot + 1
        return True
    if positions:
        return True
    if hhmm > exit_:
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['expanded_slot'] = slot + 1
            st['last_action'] = f'{now_short()} {slot + 1}차 시간누락 관망'
        return True
    if entry <= hhmm <= (entry[:3] + str(min(9, int(entry[3:]) + 4)) if int(entry[3:]) <= 5 else entry):
        sym, reason = _expanded_pick(ai_id, slot, entry)
        ok = bool(sym) and _multi_ai_buy(ai_id, sym, reason + f' decision_data_end={now_text()}', 0.9)
        with LOCK:
            st = S['paper_ais'][ai_id]
            st['last_decision_ts'] = now_ts
            if not ok:
                st['expanded_slot'] = slot + 1
                st['last_action'] = f'{now_short()} {slot + 1}차 관망 {reason}'
        return True
    return True

def run_multi_paper_ais():
    """90개 독립 가상계좌. 실제 주문 함수는 절대 호출하지 않는다."""
    ensure_multi_ai_states()
    for ai_id in MULTI_AI_IDS:
        _multi_ai_update(ai_id)
    _record_multi_ai_daily_assets()
    for ai_id in [x for x in MULTI_AI_IDS if x.startswith('L')]:
        _select_learning_sources(ai_id, False)
    if not ENABLE_MULTI_PAPER_AI or not paper_auto_time_open():
        return
    mode = target_market_regime()
    now_ts = time.time()
    hhmm = now_kst().strftime('%H:%M')
    if any((x.startswith('G') for x in MULTI_AI_IDS)):
        scan_full_market_universe(False)
    for ai_id in MULTI_AI_IDS:
        if ai_id in {'V01', 'V02', 'V03'}:
            _run_verified_fixed_account(ai_id, hhmm, now_ts)
            continue
        if ai_id.startswith('V'):
            _run_expanded_account(ai_id, hhmm, now_ts)
            continue
        if ai_id.startswith('C'):
            _run_combo_account(ai_id, mode, hhmm, now_ts)
            continue
        with LOCK:
            st = S['paper_ais'][ai_id]
            positions = dict(st.get('positions', {}))
            last_ts = to_float(st.get('last_decision_ts', 0))
        if positions:
            for sym, pos in list(positions.items()):
                reason = _multi_ai_exit_reason(ai_id, sym, pos, mode, hhmm)
                if reason:
                    ensure_live_orderbook(sym)
                    _multi_ai_sell(ai_id, sym, reason)
            continue
        if now_ts - last_ts < MULTI_AI_DECISION_COOLDOWN_SEC:
            continue
        if not _multi_ai_entry_window(ai_id, hhmm):
            continue
        parent = _multi_ai_parent_id(ai_id)
        family = _multi_ai_family(ai_id)
        if parent == 'W15' and mode in ['CHOPPY', 'NO_TRADE', 'RECOVERY']:
            with LOCK:
                st['last_decision_ts'] = now_ts
                st['last_action'] = f'{now_short()} 현금관망 {mode}'
            continue
        metric, sym, score, r3, r10, from_high, from_low, rel = _multi_ai_candidate(ai_id, mode)
        threshold = 46 if ai_id.startswith('L') else 48 if family == 'G' else 42 if family == 'W' else 40
        if not sym or metric < threshold:
            with LOCK:
                st['last_decision_ts'] = now_ts
                st['decision_data_end'] = now_text()
                st['last_action'] = f'{now_short()} 관망 mode={mode} metric={metric:.1f}'
            continue
        if family == 'G' and (not ensure_live_orderbook(sym)):
            with LOCK:
                st['last_decision_ts'] = now_ts
                st['last_action'] = f'{now_short()} 호가미수신 관망 {sym}'
            continue
        ratios = {'G01': 0.6, 'G02': 0.7, 'G03': 0.55, 'G04': 0.5, 'G05': 0.65, 'W15': 0.3, 'R12': 0.35, 'R13': 0.4, 'L01': 0.7, 'L02': 0.55, 'L03': 0.65, 'L04': 0.5, 'L05': 0.35}
        ratio = ratios.get(parent, 0.7)
        reason = f'{MULTI_AI_NAMES[ai_id]} group={MULTI_AI_GROUP[ai_id]}, universe={MULTI_AI_UNIVERSE[ai_id]}, parent={parent}, mode={mode}, metric={metric:.1f}, score={score:.1f}, r3={r3:.2f}%, r10={r10:.2f}%, high={from_high:.2f}%, low={from_low:.2f}%, rel={rel:.2f}%, decision_data_end={now_text()}'
        if _multi_ai_buy(ai_id, sym, reason, ratio):
            with LOCK:
                st['last_decision_ts'] = now_ts
                st['last_decision_date'] = today()
                st['decision_data_end'] = now_text()

def simulated_orderbook_fill(sym, side, max_cash=0, qty=0):
    """현재 호가 잔량을 위에서부터 소진해 가상 평균체결가/부분체결을 계산한다."""
    ob = S.setdefault('market_data_capture', {}).get('latest_orderbook', {}).get(sym, {})
    levels = ob.get('asks' if side == 'BUY' else 'bids', []) if isinstance(ob, dict) else []
    if not isinstance(levels, list) or not levels:
        return {'ok': False, 'reason': 'ORDERBOOK_EMPTY', 'qty': 0, 'avg_price': 0, 'gross': 0}
    remain_cash = float(max_cash)
    remain_qty = int(qty)
    filled = 0
    gross = 0.0
    for level in levels:
        if not isinstance(level, dict):
            continue
        px = to_float(level.get('price', 0))
        avail = int(to_float(level.get('volume', 0)))
        if px <= 0 or avail <= 0:
            continue
        if side == 'BUY':
            can = min(avail, int(remain_cash // px))
        else:
            can = min(avail, remain_qty)
        if can <= 0:
            continue
        filled += can
        gross += can * px
        if side == 'BUY':
            remain_cash -= can * px
        else:
            remain_qty -= can
        if side == 'BUY' and remain_cash < px or (side == 'SELL' and remain_qty <= 0):
            break
    return {'ok': filled > 0, 'reason': 'OK' if filled > 0 else 'NO_LIQUIDITY', 'qty': filled, 'avg_price': gross / filled if filled else 0, 'gross': gross, 'partial': side == 'SELL' and filled < qty, 'orderbook_timestamp': ob.get('timestamp', '') if isinstance(ob, dict) else ''}

def _result_dict(data):
    if not isinstance(data, dict):
        return {}
    result = data.get('result', data)
    return result if isinstance(result, dict) else {}

def _market_data_request_gap():
    """26종목 동등 수집 중 API 요청 폭주를 막는다."""
    if MARKET_DATA_REQUEST_GAP_SEC > 0:
        time.sleep(MARKET_DATA_REQUEST_GAP_SEC)

def capture_kr_prices_all26():
    """공식 /prices 한 번으로 26종목을 같은 요청시각·형식으로 저장한다."""
    requested = now_kst()
    started = time.time()
    code, data = api_get('/api/v1/prices', params={'symbols': ','.join(ALL26_SYMBOLS)}, timeout=10)
    received = now_kst()
    latency = round((time.time() - started) * 1000, 3)
    if code != 200:
        return (False, [f'PRICES_HTTP_{code}'])
    result = data.get('result', []) if isinstance(data, dict) else []
    seen = set()
    headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'last_price', 'currency']
    for item in result if isinstance(result, list) else []:
        if not isinstance(item, dict):
            continue
        sym = str(item.get('symbol', ''))
        if sym not in ALL26_SYMBOLS:
            continue
        seen.add(sym)
        write_row(price_snapshot_path(sym), headers, {'requested_at': requested.isoformat(), 'received_at': received.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': item.get('timestamp', ''), 'last_price': item.get('lastPrice', 0), 'currency': item.get('currency', 'KRW')})
    missing = [s for s in ALL26_SYMBOLS if s not in seen]
    return (not missing, [f'{s}:PRICE_MISSING' for s in missing])

def capture_candles_1m():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    state = S.setdefault('market_data_capture', {})
    headers = ['saved_at', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']

    def save_candles(sym, candles, currency_default):
        path = candle_1m_path(sym)
        cal = state.get('calendar', {})
        for c in reversed(candles if isinstance(candles, list) else []):
            if not isinstance(c, dict):
                continue
            ts = str(c.get('timestamp', ''))
            if not ts or not _completed_session_candle(ts, cal.get('date', today()), cal.get('regular_start', ''), cal.get('regular_end', '')):
                continue
            row = {'saved_at': now_text(), 'symbol': sym, 'timestamp': ts, 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'estimated_trade_value': round(to_float(c.get('closePrice', 0)) * to_float(c.get('volume', 0)), 4), 'currency': c.get('currency', currency_default)}
            if write_row_unique(path, headers, row, ['symbol', 'timestamp']):
                state.setdefault('last_candle_minute', {})[sym] = f'{sym}:{ts}'
    for sym in MARKET_DATA_CORE_SYMBOLS:
        code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': max(1, min(200, MARKET_DATA_CANDLE_COUNT)), 'adjusted': True}, timeout=10)
        if code == 200:
            result = _result_dict(data)
            save_candles(sym, result.get('candles', []), 'KRW')
    for sym in ['KOSPI', 'KOSDAQ']:
        code, data = api_get(f'/api/v1/market-indicators/{sym}/candles', params={'interval': '1m', 'count': max(1, min(10, MARKET_DATA_CANDLE_COUNT))}, timeout=10)
        if code == 200:
            result = _result_dict(data)
            save_candles(sym, result.get('candles', []), 'INDEX')

def capture_orderbook_and_trades():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    market_ok, _market_reason = regular_market_open_now()
    if not market_ok:
        return
    state = S.setdefault('market_data_capture', {})
    ob_headers = ['saved_at', 'symbol', 'api_timestamp', 'best_ask', 'best_bid', 'spread', 'ask_total_volume', 'bid_total_volume', 'bid_ask_ratio', 'asks_json', 'bids_json']
    tr_headers = ['saved_at', 'symbol', 'timestamp', 'price', 'volume', 'trade_value', 'currency']
    for sym in MARKET_DATA_ORDERFLOW_SYMBOLS:
        code, data = api_get('/api/v1/orderbook', params={'symbol': sym}, timeout=8)
        _market_data_request_gap()
        if code == 200:
            result = _result_dict(data)
            asks = result.get('asks', []) if isinstance(result.get('asks', []), list) else []
            bids = result.get('bids', []) if isinstance(result.get('bids', []), list) else []
            api_ts = str(result.get('timestamp', ''))
            if api_ts and state.setdefault('last_orderbook_timestamp', {}).get(sym) != api_ts:
                ask_total = sum((to_float(x.get('volume', 0)) for x in asks if isinstance(x, dict)))
                bid_total = sum((to_float(x.get('volume', 0)) for x in bids if isinstance(x, dict)))
                best_ask = to_float(asks[0].get('price', 0)) if asks else 0
                best_bid = to_float(bids[0].get('price', 0)) if bids else 0
                state.setdefault('latest_orderbook', {})[sym] = {'timestamp': api_ts, 'best_ask': best_ask, 'best_bid': best_bid, 'asks': asks, 'bids': bids}
                write_row(orderbook_path(sym), ob_headers, {'saved_at': now_text(), 'symbol': sym, 'api_timestamp': api_ts, 'best_ask': best_ask, 'best_bid': best_bid, 'spread': best_ask - best_bid if best_ask and best_bid else 0, 'ask_total_volume': int(ask_total), 'bid_total_volume': int(bid_total), 'bid_ask_ratio': round(bid_total / ask_total, 4) if ask_total else 0, 'asks_json': json.dumps(asks, ensure_ascii=False, separators=(',', ':')), 'bids_json': json.dumps(bids, ensure_ascii=False, separators=(',', ':'))})
                state['last_orderbook_timestamp'][sym] = api_ts
        code, data = api_get('/api/v1/trades', params={'symbol': sym, 'count': max(1, min(50, MARKET_DATA_TRADE_COUNT))}, timeout=8)
        _market_data_request_gap()
        if code != 200:
            continue
        result = data.get('result', []) if isinstance(data, dict) else []
        if not isinstance(result, list):
            continue
        last_seen = state.setdefault('last_trade_timestamp', {}).get(sym, '')
        new_rows = []
        for t in reversed(result):
            if not isinstance(t, dict):
                continue
            ts = str(t.get('timestamp', ''))
            if not ts or (last_seen and ts <= last_seen):
                continue
            new_rows.append(t)
        for t in new_rows:
            write_row(trades_path(sym), tr_headers, {'saved_at': now_text(), 'symbol': sym, 'timestamp': t.get('timestamp', ''), 'price': t.get('price', 0), 'volume': t.get('volume', 0), 'trade_value': round(to_float(t.get('price', 0)) * to_float(t.get('volume', 0)), 4), 'currency': t.get('currency', 'KRW')})
        if new_rows:
            last_trade = new_rows[-1]
            state['last_trade_timestamp'][sym] = str(last_trade.get('timestamp', ''))
            state.setdefault('latest_trade', {})[sym] = {'timestamp': str(last_trade.get('timestamp', '')), 'price': to_float(last_trade.get('price', 0)), 'volume': to_float(last_trade.get('volume', 0))}

def capture_us_market_data():
    """미국 정규장 전용 수집. 한국 파일·상태와 절대 섞지 않는다."""
    if not ENABLE_US_MARKET_DATA_CAPTURE:
        return
    opened, reason = us_regular_market_open_now()
    state = S.setdefault('us_market_data_capture', {})
    if not opened:
        state['status'] = reason
        return
    cal = state.get('calendar', {})
    now_ts = time.time()
    candle_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    ob_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'api_timestamp', 'best_ask', 'best_bid', 'spread', 'ask_total_volume', 'bid_total_volume', 'asks_json', 'bids_json']
    tr_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'price', 'volume', 'trade_value', 'currency']
    if now_ts - to_float(state.get('last_price_ts', 0)) >= US_ORDERFLOW_SEC:
        req = now_kst()
        t0 = time.time()
        code, data = api_get('/api/v1/prices', params={'symbols': ','.join(US_SYMBOLS)}, timeout=10)
        rec = now_kst()
        latency = round((time.time() - t0) * 1000, 3)
        if code == 200:
            result = data.get('result', []) if isinstance(data, dict) else []
            headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'last_price', 'currency']
            for item in result if isinstance(result, list) else []:
                if not isinstance(item, dict):
                    continue
                sym = str(item.get('symbol', '')).upper()
                if sym not in US_SYMBOLS:
                    continue
                write_row(us_data_path('prices', sym), headers, {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': item.get('timestamp', ''), 'last_price': item.get('lastPrice', 0), 'currency': item.get('currency', 'USD')})
        state['last_price_ts'] = now_ts
    if now_ts - to_float(state.get('last_candle_ts', 0)) >= US_CANDLE_SEC:
        for sym in US_SYMBOLS:
            req = now_kst()
            t0 = time.time()
            code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': 200, 'adjusted': True}, timeout=10)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if code == 200:
                candles = _result_dict(data).get('candles', [])
                for c in reversed(candles if isinstance(candles, list) else []):
                    ts = str(c.get('timestamp', ''))
                    if not _completed_session_candle(ts, None, cal.get('regular_start'), cal.get('regular_end')):
                        continue
                    close = to_float(c.get('closePrice', 0))
                    volume = to_float(c.get('volume', 0))
                    write_row_unique(us_data_path('candles_1m', sym), candle_headers, {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': ts, 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'estimated_trade_value': round(close * volume, 4), 'currency': c.get('currency', 'USD')}, ['symbol', 'timestamp'])
            _market_data_request_gap()
        state['last_candle_ts'] = now_ts
    if now_ts - to_float(state.get('last_orderflow_ts', 0)) >= US_ORDERFLOW_SEC:
        for sym in US_SYMBOLS:
            req = now_kst()
            t0 = time.time()
            code, data = api_get('/api/v1/orderbook', params={'symbol': sym}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if code == 200:
                result = _result_dict(data)
                asks = result.get('asks', []) if isinstance(result.get('asks', []), list) else []
                bids = result.get('bids', []) if isinstance(result.get('bids', []), list) else []
                api_ts = str(result.get('timestamp', ''))
                ask_total = sum((to_float(x.get('volume', 0)) for x in asks if isinstance(x, dict)))
                bid_total = sum((to_float(x.get('volume', 0)) for x in bids if isinstance(x, dict)))
                write_row_unique(us_data_path('orderbook', sym), ob_headers, {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'api_timestamp': api_ts, 'best_ask': asks[0].get('price', 0) if asks else 0, 'best_bid': bids[0].get('price', 0) if bids else 0, 'spread': to_float(asks[0].get('price', 0)) - to_float(bids[0].get('price', 0)) if asks and bids else 0, 'ask_total_volume': ask_total, 'bid_total_volume': bid_total, 'asks_json': json.dumps(asks, separators=(',', ':')), 'bids_json': json.dumps(bids, separators=(',', ':'))}, ['symbol', 'api_timestamp'])
            _market_data_request_gap()
            req = now_kst()
            t0 = time.time()
            code, data = api_get('/api/v1/trades', params={'symbol': sym, 'count': 50}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if code == 200:
                trades = data.get('result', []) if isinstance(data, dict) else []
                for t in reversed(trades if isinstance(trades, list) else []):
                    ts = str(t.get('timestamp', ''))
                    price = to_float(t.get('price', 0))
                    volume = to_float(t.get('volume', 0))
                    if not ts:
                        continue
                    write_row_unique(us_data_path('trades', sym), tr_headers, {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': ts, 'price': t.get('price', 0), 'volume': t.get('volume', 0), 'trade_value': round(price * volume, 4), 'currency': t.get('currency', 'USD')}, ['symbol', 'timestamp', 'price', 'volume'])
            _market_data_request_gap()
        state['last_orderflow_ts'] = now_ts
    if now_ts - to_float(state.get('last_metadata_ts', 0)) >= US_METADATA_REFRESH_SEC:
        daily_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'currency']
        meta_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'stock_http', 'warning_http', 'limits_http', 'stock_json', 'warning_json', 'limits_json']
        for sym in US_SYMBOLS:
            req = now_kst()
            t0 = time.time()
            code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1d', 'count': 200, 'adjusted': True}, timeout=12)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if code == 200:
                candles = _result_dict(data).get('candles', [])
                rows = []
                for c in reversed(candles if isinstance(candles, list) else []):
                    if not isinstance(c, dict):
                        continue
                    rows.append({'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': c.get('timestamp', ''), 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'currency': c.get('currency', 'USD')})
                _rewrite_csv(us_data_path('candles_1d', sym), daily_headers, rows)
            _market_data_request_gap()
            req = now_kst()
            t0 = time.time()
            c1, d1 = api_get('/api/v1/stocks', params={'symbols': sym}, timeout=8)
            _market_data_request_gap()
            c2, d2 = api_get(f'/api/v1/stocks/{sym}/warnings', timeout=8)
            _market_data_request_gap()
            c3, d3 = api_get('/api/v1/price-limits', params={'symbol': sym}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            _rewrite_csv(us_data_path('metadata', sym), meta_headers, [{'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'stock_http': c1, 'warning_http': c2, 'limits_http': c3, 'stock_json': json.dumps(d1, ensure_ascii=False, separators=(',', ':'))[:10000], 'warning_json': json.dumps(d2, ensure_ascii=False, separators=(',', ':'))[:10000], 'limits_json': json.dumps(d3, ensure_ascii=False, separators=(',', ':'))[:10000]}])
        state['last_metadata_ts'] = now_ts
    state['status'] = 'COLLECTING'

def capture_daily_candles_all26():
    """26개 전 종목 일봉을 같은 형식으로 저장한다."""
    headers = ['saved_at', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    for sym in MARKET_DATA_DAILY_SYMBOLS:
        code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1d', 'count': MARKET_DATA_DAILY_COUNT, 'adjusted': True}, timeout=12)
        _market_data_request_gap()
        if code != 200:
            continue
        result = _result_dict(data)
        candles = result.get('candles', []) if isinstance(result, dict) else []
        if not isinstance(candles, list):
            continue
        path = candle_daily_path(sym)
        tmp = path + '.tmp'
        try:
            with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                for c in reversed(candles):
                    if not isinstance(c, dict):
                        continue
                    w.writerow({'saved_at': now_text(), 'symbol': sym, 'timestamp': c.get('timestamp', ''), 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'estimated_trade_value': round(to_float(c.get('closePrice', 0)) * to_float(c.get('volume', 0)), 4), 'currency': c.get('currency', 'KRW')})
            os.replace(tmp, path)
        except Exception as e:
            set_error(f'일봉 저장 실패 {sym}: {e}')

def capture_stock_metadata_all26():
    """종목정보·경고·상하한가를 26개 모두 동일하게 수집한다."""
    headers = ['saved_at', 'symbol', 'name', 'stock_http', 'warning_http', 'limits_http', 'stock_json', 'warning_json', 'limits_json']
    for sym in MARKET_DATA_METADATA_SYMBOLS:
        c1, d1 = api_get('/api/v1/stocks', params={'symbols': sym}, timeout=8)
        _market_data_request_gap()
        c2, d2 = api_get(f'/api/v1/stocks/{sym}/warnings', timeout=8)
        _market_data_request_gap()
        c3, d3 = api_get('/api/v1/price-limits', params={'symbol': sym}, timeout=8)
        _market_data_request_gap()
        write_row(stock_metadata_path(sym), headers, {'saved_at': now_text(), 'symbol': sym, 'name': name_of(sym), 'stock_http': c1, 'warning_http': c2, 'limits_http': c3, 'stock_json': json.dumps(d1, ensure_ascii=False, separators=(',', ':'))[:10000], 'warning_json': json.dumps(d2, ensure_ascii=False, separators=(',', ':'))[:10000], 'limits_json': json.dumps(d3, ensure_ascii=False, separators=(',', ':'))[:10000]})

def write_data_quality_audit_all26():
    """전략 실행 전 확인 가능한 26개 데이터 무결성 감사표."""
    headers = ['time', 'date', 'symbol', 'name', 'snapshot_rows', 'candle_rows', 'unique_prices', 'first_price', 'low', 'high', 'last_price', 'price_age_sec', 'orderbook_age_sec', 'trade_age_sec', 'status', 'reason']
    cap = S.setdefault('market_data_capture', {})
    for sym in ALL26_SYMBOLS:
        snap_path = symbol_path(sym)
        candle_path = candle_1m_path(sym)
        prices = []
        snapshot_rows = 0
        candle_rows = 0
        try:
            if os.path.exists(snap_path):
                with open(snap_path, newline='', encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        snapshot_rows += 1
                        px = to_float(row.get('price', 0))
                        if px > 0:
                            prices.append(px)
            if os.path.exists(candle_path):
                with open(candle_path, newline='', encoding='utf-8-sig') as f:
                    candle_rows = sum((1 for _ in csv.DictReader(f)))
        except Exception:
            pass
        price_age = data_age_seconds(cap.get('price_timestamp', {}).get(sym))
        ob_age = data_age_seconds(cap.get('latest_orderbook', {}).get(sym, {}).get('timestamp'))
        tr_age = data_age_seconds(cap.get('latest_trade', {}).get(sym, {}).get('timestamp'))
        reasons = []
        if not prices:
            reasons.append('MISSING_PRICE')
        if candle_rows == 0:
            reasons.append('MISSING_1M')
        if price_age > MAX_PRICE_AGE_SEC:
            reasons.append('STALE_PRICE')
        if ob_age > MAX_ORDERBOOK_AGE_SEC:
            reasons.append('STALE_ORDERBOOK')
        status = 'OK' if not reasons else '|'.join(reasons)
        write_row(data_quality_audit_path(), headers, {'time': now_text(), 'date': today(), 'symbol': sym, 'name': name_of(sym), 'snapshot_rows': snapshot_rows, 'candle_rows': candle_rows, 'unique_prices': len(set(prices)), 'first_price': prices[0] if prices else 0, 'low': min(prices) if prices else 0, 'high': max(prices) if prices else 0, 'last_price': prices[-1] if prices else 0, 'price_age_sec': round(price_age, 1), 'orderbook_age_sec': round(ob_age, 1), 'trade_age_sec': round(tr_age, 1), 'status': status, 'reason': ','.join(reasons)})

def capture_market_investor_data():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    price_headers = ['saved_at', 'symbol', 'timestamp', 'last_price']
    code, data = api_get('/api/v1/market-indicators/prices', params={'symbols': 'KOSPI,KOSDAQ'}, timeout=8)
    if code == 200:
        result = data.get('result', []) if isinstance(data, dict) else []
        for item in result if isinstance(result, list) else []:
            if not isinstance(item, dict):
                continue
            write_row(market_indicator_path(), price_headers, {'saved_at': now_text(), 'symbol': item.get('symbol', ''), 'timestamp': item.get('timestamp', ''), 'last_price': item.get('lastPrice', 0)})
    headers = ['saved_at', 'market', 'date', 'updated_at', 'individual_buy', 'individual_sell', 'individual_net', 'foreigner_buy', 'foreigner_sell', 'foreigner_net', 'institution_buy', 'institution_sell', 'institution_net', 'other_corp_buy', 'other_corp_sell', 'other_corp_net', 'institution_breakdown_json']
    for market in ['KOSPI', 'KOSDAQ']:
        code, data = api_get(f'/api/v1/market-indicators/{market}/investor-trading', params={'interval': '1d', 'count': 1}, timeout=10)
        if code != 200:
            continue
        result = _result_dict(data)
        records = result.get('records', []) if isinstance(result, dict) else []
        if not records or not isinstance(records[0], dict):
            continue
        r = records[0]

        def amounts(key):
            obj = r.get(key, {}) if isinstance(r.get(key, {}), dict) else {}
            buy = to_int(obj.get('buyAmount', 0))
            sell = to_int(obj.get('sellAmount', 0))
            return (buy, sell, buy - sell)
        ib, isell, inet = amounts('individual')
        fb, fs, fnet = amounts('foreigner')
        nb, ns, nnet = amounts('institution')
        ob, osell, onet = amounts('otherCorporation')
        inst = r.get('institution', {}) if isinstance(r.get('institution', {}), dict) else {}
        write_row(investor_trading_path(), headers, {'saved_at': now_text(), 'market': market, 'date': r.get('date', ''), 'updated_at': r.get('updatedAt', ''), 'individual_buy': ib, 'individual_sell': isell, 'individual_net': inet, 'foreigner_buy': fb, 'foreigner_sell': fs, 'foreigner_net': fnet, 'institution_buy': nb, 'institution_sell': ns, 'institution_net': nnet, 'other_corp_buy': ob, 'other_corp_sell': osell, 'other_corp_net': onet, 'institution_breakdown_json': json.dumps(inst.get('breakdown', {}), ensure_ascii=False, separators=(',', ':'))})

def maybe_capture_toss_market_data():
    if not ENABLE_TOSS_MARKET_DATA_CAPTURE:
        return
    market_ok, market_reason = regular_market_open_now()
    if not market_ok:
        S.setdefault('market_data_capture', {})['status'] = f'수집대기:{market_reason}'
        return
    state = S.setdefault('market_data_capture', {})
    now_ts = time.time()
    try:
        if now_ts - to_float(state.get('last_price_snapshot_ts', 0)) >= MARKET_DATA_ORDERFLOW_SEC:
            capture_kr_prices_all26()
            state['last_price_snapshot_ts'] = now_ts
        if now_ts - to_float(state.get('last_candle_ts', 0)) >= MARKET_DATA_CANDLE_SEC:
            capture_candles_1m()
            state['last_candle_ts'] = now_ts
        repair_kr_first_candle_during_open()
        if now_ts - to_float(state.get('last_orderflow_ts', 0)) >= MARKET_DATA_ORDERFLOW_SEC:
            capture_orderbook_and_trades()
            state['last_orderflow_ts'] = now_ts
        if now_ts - to_float(state.get('last_investor_ts', 0)) >= MARKET_DATA_INVESTOR_SEC:
            capture_market_investor_data()
            state['last_investor_ts'] = now_ts
        if now_ts - to_float(state.get('last_daily_ts', 0)) >= MARKET_DATA_DAILY_REFRESH_SEC:
            capture_daily_candles_all26()
            state['last_daily_ts'] = now_ts
        if now_ts - to_float(state.get('last_metadata_ts', 0)) >= MARKET_DATA_METADATA_REFRESH_SEC:
            capture_stock_metadata_all26()
            state['last_metadata_ts'] = now_ts
        if now_ts - to_float(state.get('last_audit_ts', 0)) >= MARKET_DATA_AUDIT_SEC:
            write_data_quality_audit_all26()
            state['last_audit_ts'] = now_ts
        state['status'] = '정상'
    except Exception as e:
        state['errors'] = to_int(state.get('errors', 0)) + 1
        state['status'] = f'오류: {e}'
        set_error(f'토스 시장데이터 수집 오류: {e}')

def write_logs():
    hs = ['time', 'symbol', 'name', 'price', 'high', 'low', 'wma5', 'wma20', 'wma60', 'volume_ratio', 'score', 'signal', 'market_score', 'market_label', 'news_score', 'news_label', 'rec_buy_qty', 'rec_sell_qty']
    with LOCK:
        signals = dict(S['signals'])
        prices = dict(S['prices'])
        highs = dict(S['high'])
        lows = dict(S['low'])
        wmas = dict(S['wma'])
        market_score = dict(S['market_score'])
        news = {'score': 0, 'label': 'REMOVED'}
    for sym in ALL:
        price = prices.get(sym, 0)
        if price <= 0:
            continue
        wm = wmas.get(sym, {})
        sig = signals.get(sym, {})
        row = {'time': now_text(), 'symbol': sym, 'name': name_of(sym), 'price': price, 'high': highs.get(sym, price), 'low': lows.get(sym, price), 'wma5': wm.get('wma5', 0), 'wma20': wm.get('wma20', 0), 'wma60': wm.get('wma60', 0), 'volume_ratio': wm.get('volume_ratio', 1), 'score': sig.get('score', 0), 'signal': sig.get('label', ''), 'market_score': market_score.get('total', 0), 'market_label': market_score.get('label', ''), 'news_score': news.get('score', 0), 'news_label': news.get('label', ''), 'rec_buy_qty': sig.get('rec_buy_qty', 0), 'rec_sell_qty': sig.get('rec_sell_qty', 0)}
        write_row(summary_path(), hs, row)
        write_row(symbol_path(sym), hs, row)
    # 실계좌 포트폴리오/스윙 로그는 데이터·가상매매 전용 빌드에서 생성하지 않는다.

def finalize_all_paper_accounts():
    """매매가 없어도 90개 계좌 모두 당일 평가·상태 파일을 남긴다."""
    ensure_multi_ai_states()
    for ai_id in MULTI_AI_IDS:
        _multi_ai_update(ai_id)
        with LOCK:
            st = dict(S['paper_ais'][ai_id])
        state_path = multi_ai_state_path(ai_id)
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        state_tmp = state_path + '.tmp'
        with open(state_tmp, 'w', encoding='utf-8') as f:
            json.dump({'saved_at': now_text(), 'date': today(), 'ai_id': ai_id, 'ai_name': st.get('name', ai_id), 'start_cash': int(to_float(st.get('start_cash', MULTI_AI_START_CASH))), 'cash': int(to_float(st.get('cash', 0))), 'asset': int(to_float(st.get('asset', 0))), 'profit_rate': round(to_float(st.get('profit_rate', 0)), 6), 'positions': st.get('positions', {}), 'last_action': st.get('last_action', '초기화'), 'paper_only': True, 'real_order': False}, f, ensure_ascii=False, indent=2)
        os.replace(state_tmp, state_path)
        path = multi_ai_path(ai_id)
        existing = _read_csv_rows(path)
        if existing:
            continue
        row = {'time': now_text(), 'ai_id': ai_id, 'ai_name': st.get('name', ai_id), 'action': '가상관망', 'symbol': '', 'name': '', 'price': 0, 'qty': 0, 'fee': 0, 'pl': 0, 'cash': int(to_float(st.get('cash', 0))), 'asset': int(to_float(st.get('asset', 0))), 'profit_rate': round(to_float(st.get('profit_rate', 0)), 4), 'reason': 'NO_TRADE_EVALUATED; last_action=' + str(st.get('last_action', '초기화')), 'partial': False, 'real_order': False}
        write_row(path, ['time', 'ai_id', 'ai_name', 'action', 'symbol', 'name', 'price', 'qty', 'fee', 'pl', 'cash', 'asset', 'profit_rate', 'reason', 'partial', 'real_order'], row)

def _completed_kr_trading_candle(ts, session_date, session_start, session_end, now_value=None):
    """
    국내 1분봉은 실제 원본에서 분 구간의 종료시각으로 라벨된다.
    정규장 09:00~15:30의 390개 거래분봉은 09:01~15:30이다.
    09:00의 0거래량 기준봉은 거래분봉 집계에서 제외한다.
    """
    dt = _parse_iso(ts)
    start = _parse_iso(session_start)
    end = _parse_iso(session_end)
    now_value = now_value or now_kst()
    if not dt or not start or (not end):
        return False
    if session_date and dt.astimezone(KST).date().isoformat() != str(session_date):
        return False
    current_minute = now_value.replace(second=0, microsecond=0)
    return start < dt <= end and dt < current_minute

def _kr_expected_candle_times(start, end):
    count = int((end - start).total_seconds() // 60)
    return [start + timedelta(minutes=i) for i in range(1, count + 1)]

def _kr_candle_csv_row(sym, candle):
    close = to_float(candle.get('closePrice', 0))
    volume = to_float(candle.get('volume', 0))
    return {'saved_at': now_text(), 'symbol': sym, 'timestamp': str(candle.get('timestamp', '')), 'open': candle.get('openPrice', 0), 'high': candle.get('highPrice', 0), 'low': candle.get('lowPrice', 0), 'close': candle.get('closePrice', 0), 'volume': candle.get('volume', 0), 'estimated_trade_value': round(close * volume, 4), 'currency': candle.get('currency', 'KRW')}

def _fetch_kr_candle_at(sym, target, cal):
    """
    토스 공식 Open API 1.2.9의 before는 inclusive다.
    before=target을 그대로 사용하고, 정확히 target과 일치하는 봉만 저장한다.
    """
    attempts = []
    for attempt in range(1, KR_TARGETED_BACKFILL_RETRIES + 1):
        before_iso = target.isoformat()
        code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': 3, 'before': before_iso, 'adjusted': True}, timeout=12)
        result = _result_dict(data)
        candles = result.get('candles', []) if isinstance(result, dict) else []
        returned = [str(item.get('timestamp', '')) for item in candles if isinstance(item, dict)]
        attempts.append({'attempt': attempt, 'http': code, 'target': target.isoformat(), 'before': before_iso, 'returned': returned})
        if code == 200:
            for candle in candles if isinstance(candles, list) else []:
                if not isinstance(candle, dict):
                    continue
                if _parse_iso(candle.get('timestamp')) != target:
                    continue
                if not _completed_kr_trading_candle(candle.get('timestamp'), cal.get('date'), cal.get('regular_start'), cal.get('regular_end')):
                    continue
                return (_kr_candle_csv_row(sym, candle), attempts)
        time.sleep(min(0.8 * attempt, 4.0))
        _market_data_request_gap()
    return (None, attempts)

def _merge_kr_candle_rows(sym, new_rows):
    headers = ['saved_at', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    merged = {}
    for row in _read_csv_rows(candle_1m_path(sym)):
        ts = str(row.get('timestamp', ''))
        if ts:
            merged[ts] = {k: row.get(k, '') for k in headers}
    for row in new_rows:
        ts = str(row.get('timestamp', ''))
        if ts:
            merged[ts] = row
    _rewrite_csv(candle_1m_path(sym), headers, [merged[k] for k in sorted(merged)])

def repair_kr_first_candle_during_open():
    """09:02~09:15에 26종목의 첫 거래분봉(09:01)을 반복 검사한다."""
    state = S.setdefault('market_data_capture', {})
    cal = state.get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    if not start or cal.get('date') != today():
        return
    n = now_kst()
    if n.date() != start.astimezone(KST).date():
        return
    minute_from_open = int((n - start).total_seconds() // 60)
    if not KR_FIRST_CANDLE_REPAIR_START_MIN <= minute_from_open <= KR_FIRST_CANDLE_REPAIR_END_MIN:
        return
    minute_key = f"{today()}_{n.strftime('%H:%M')}"
    if state.get('first_candle_repair_minute_key') == minute_key:
        return
    state['first_candle_repair_minute_key'] = minute_key
    failures = []
    for sym in ALL26_SYMBOLS:
        existing = {_parse_iso(x.get('timestamp')) for x in _read_csv_rows(candle_1m_path(sym))}
        first_trade_candle = start + timedelta(minutes=1)
        if first_trade_candle in existing:
            continue
        row, attempts = _fetch_kr_candle_at(sym, first_trade_candle, cal)
        if row:
            _merge_kr_candle_rows(sym, [row])
        else:
            failures.append({'symbol': sym, 'target': first_trade_candle.isoformat(), 'attempts': attempts})
    state['first_candle_repair_last_at'] = now_text()
    state['first_candle_repair_failures'] = failures

def finalize_kr_candles_grade1():
    """기존 정상 봉을 보존하며 공식 페이지네이션으로 정규장 완성봉을 복구한다."""
    state = S.setdefault('market_data_capture', {})
    refresh_kr_market_calendar(True)
    cal = state.get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))
    if not start or not end or cal.get('date') != today():
        return (False, ['KR_CALENDAR_INVALID'])
    headers = ['saved_at', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    failures = []
    for sym in MARKET_DATA_CORE_SYMBOLS:
        collected = {}
        for row in _read_csv_rows(candle_1m_path(sym)):
            ts = str(row.get('timestamp', ''))
            dt = _parse_iso(ts)
            if dt and start < dt <= end:
                collected[ts] = {k: row.get(k, '') for k in headers}
        before = end.isoformat()
        seen = set()
        for _ in range(4):
            if before in seen:
                break
            seen.add(before)
            code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': 200, 'before': before, 'adjusted': True}, timeout=12)
            if code != 200:
                failures.append(f'{sym}:HTTP_{code}')
                # 인증 실패면 나머지 25종목까지 같은 401을 반복하지 않는다.
                # 기존 수집 원본은 create_backup_zip() 진입 직후 RAW 구조백업으로 이미 보존된다.
                if code == 401:
                    return (False, failures)
                break
            result = _result_dict(data)
            candles = result.get('candles', []) if isinstance(result, dict) else []
            page_times = []
            for c in candles if isinstance(candles, list) else []:
                ts = str(c.get('timestamp', ''))
                if _completed_kr_trading_candle(ts, None, cal.get('regular_start'), cal.get('regular_end')):
                    dt = _parse_iso(ts)
                    if dt:
                        page_times.append(dt)
                    collected[ts] = {'saved_at': now_text(), 'symbol': sym, 'timestamp': ts, 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'estimated_trade_value': round(to_float(c.get('closePrice', 0)) * to_float(c.get('volume', 0)), 4), 'currency': c.get('currency', 'KRW')}
            oldest = min(page_times, default=None)
            if oldest and oldest <= start:
                break
            nxt = result.get('nextBefore') if isinstance(result, dict) else None
            if not nxt:
                break
            before = str(nxt)
            _market_data_request_gap()
        expected_times = _kr_expected_candle_times(start, end)
        present = {_parse_iso(ts) for ts in collected}
        missing_times = [ts for ts in expected_times if ts not in present]
        targeted_failures = []
        for target in missing_times:
            row, attempts = _fetch_kr_candle_at(sym, target, cal)
            if row:
                collected[str(row['timestamp'])] = row
            else:
                targeted_failures.append({'target': target.isoformat(), 'attempts': attempts})
        if targeted_failures:
            failures.append(f'{sym}:TARGETED_BACKFILL_FAILED=' + json.dumps(targeted_failures, ensure_ascii=False, separators=(',', ':')))
        rows = [collected[k] for k in sorted(collected)]
        _rewrite_csv(candle_1m_path(sym), headers, rows)
        expected = int((end - start).total_seconds() // 60)
        if len(rows) != expected or not rows or _parse_iso(rows[0]['timestamp']) != start + timedelta(minutes=1) or (_parse_iso(rows[-1]['timestamp']) != end):
            failures.append(f'{sym}:CANDLES_{len(rows)}')
    return (not failures, failures)

def repair_kr_required_files_before_backup():
    """백업 직전 26종목 필수 파일을 재조회한다. 기존 정상 파일은 실패 시 보존한다."""
    failures = []
    ok, price_failures = capture_kr_prices_all26()
    if not ok:
        failures.extend(price_failures)
    daily_headers = ['saved_at', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    meta_headers = ['saved_at', 'symbol', 'name', 'stock_http', 'warning_http', 'limits_http', 'stock_json', 'warning_json', 'limits_json']
    ob_headers = ['saved_at', 'symbol', 'api_timestamp', 'best_ask', 'best_bid', 'spread', 'ask_total_volume', 'bid_total_volume', 'bid_ask_ratio', 'asks_json', 'bids_json']
    tr_headers = ['saved_at', 'symbol', 'timestamp', 'price', 'volume', 'trade_value', 'currency']
    if not _read_csv_rows(market_indicator_path()) or not _read_csv_rows(investor_trading_path()):
        capture_market_investor_data()
    if not _read_csv_rows(market_indicator_path()):
        failures.append('MARKET_INDICATORS_MISSING')
    if not _read_csv_rows(investor_trading_path()):
        failures.append('INVESTOR_TRADING_MISSING')
    for sym in ALL26_SYMBOLS:
        if not _read_csv_rows(candle_daily_path(sym)):
            c, d = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1d', 'count': MARKET_DATA_DAILY_COUNT, 'adjusted': True}, timeout=12)
            _market_data_request_gap()
            candles = _result_dict(d).get('candles', []) if c == 200 else []
            rows = []
            for x in reversed(candles if isinstance(candles, list) else []):
                if not isinstance(x, dict):
                    continue
                rows.append({'saved_at': now_text(), 'symbol': sym, 'timestamp': x.get('timestamp', ''), 'open': x.get('openPrice', 0), 'high': x.get('highPrice', 0), 'low': x.get('lowPrice', 0), 'close': x.get('closePrice', 0), 'volume': x.get('volume', 0), 'estimated_trade_value': round(to_float(x.get('closePrice', 0)) * to_float(x.get('volume', 0)), 4), 'currency': x.get('currency', 'KRW')})
            if rows:
                _rewrite_csv(candle_daily_path(sym), daily_headers, rows)
            if not _read_csv_rows(candle_daily_path(sym)):
                failures.append(f'{sym}:DAILY_HTTP_{c}')
        metadata = _read_csv_rows(stock_metadata_path(sym))
        meta_ok = bool(metadata) and all((str(metadata[-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http')))
        if not meta_ok:
            c1, d1 = api_get('/api/v1/stocks', params={'symbols': sym}, timeout=8)
            _market_data_request_gap()
            c2, d2 = api_get(f'/api/v1/stocks/{sym}/warnings', timeout=8)
            _market_data_request_gap()
            c3, d3 = api_get('/api/v1/price-limits', params={'symbol': sym}, timeout=8)
            _market_data_request_gap()
            if c1 == c2 == c3 == 200:
                _rewrite_csv(stock_metadata_path(sym), meta_headers, [{'saved_at': now_text(), 'symbol': sym, 'name': name_of(sym), 'stock_http': c1, 'warning_http': c2, 'limits_http': c3, 'stock_json': json.dumps(d1, ensure_ascii=False, separators=(',', ':'))[:10000], 'warning_json': json.dumps(d2, ensure_ascii=False, separators=(',', ':'))[:10000], 'limits_json': json.dumps(d3, ensure_ascii=False, separators=(',', ':'))[:10000]}])
            metadata = _read_csv_rows(stock_metadata_path(sym))
            if not metadata or not all((str(metadata[-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http'))):
                failures.append(f'{sym}:METADATA_HTTP_{c1}_{c2}_{c3}')
        if not _read_csv_rows(orderbook_path(sym)):
            c, d = api_get('/api/v1/orderbook', params={'symbol': sym}, timeout=8)
            _market_data_request_gap()
            r = _result_dict(d)
            asks = r.get('asks', []) if isinstance(r.get('asks', []), list) else []
            bids = r.get('bids', []) if isinstance(r.get('bids', []), list) else []
            ts = str(r.get('timestamp', ''))
            if c == 200 and ts:
                at = sum((to_float(x.get('volume', 0)) for x in asks if isinstance(x, dict)))
                bt = sum((to_float(x.get('volume', 0)) for x in bids if isinstance(x, dict)))
                ba = to_float(asks[0].get('price', 0)) if asks else 0
                bb = to_float(bids[0].get('price', 0)) if bids else 0
                write_row_unique(orderbook_path(sym), ob_headers, {'saved_at': now_text(), 'symbol': sym, 'api_timestamp': ts, 'best_ask': ba, 'best_bid': bb, 'spread': ba - bb if ba and bb else 0, 'ask_total_volume': int(at), 'bid_total_volume': int(bt), 'bid_ask_ratio': round(bt / at, 4) if at else 0, 'asks_json': json.dumps(asks, ensure_ascii=False, separators=(',', ':')), 'bids_json': json.dumps(bids, ensure_ascii=False, separators=(',', ':'))}, ['symbol', 'api_timestamp'])
            if not _read_csv_rows(orderbook_path(sym)):
                failures.append(f'{sym}:ORDERBOOK_HTTP_{c}')
        if not _read_csv_rows(trades_path(sym)):
            c, d = api_get('/api/v1/trades', params={'symbol': sym, 'count': 50}, timeout=8)
            _market_data_request_gap()
            trades = d.get('result', []) if isinstance(d, dict) else []
            if c == 200:
                for x in reversed(trades if isinstance(trades, list) else []):
                    if not isinstance(x, dict) or not x.get('timestamp'):
                        continue
                    write_row_unique(trades_path(sym), tr_headers, {'saved_at': now_text(), 'symbol': sym, 'timestamp': x.get('timestamp', ''), 'price': x.get('price', 0), 'volume': x.get('volume', 0), 'trade_value': round(to_float(x.get('price', 0)) * to_float(x.get('volume', 0)), 4), 'currency': x.get('currency', 'KRW')}, ['symbol', 'timestamp', 'price', 'volume'])
            if not _read_csv_rows(trades_path(sym)):
                failures.append(f'{sym}:TRADES_HTTP_{c}')
    return failures

def audit_kr_grade1():
    """파일명/용량이 아닌 실제 CSV 내용으로만 1등급을 판정한다."""
    cal = S.setdefault('market_data_capture', {}).get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))
    failures = []
    details = {}
    if not start or not end:
        return {'grade': 'FAILED', 'failures': ['CALENDAR_INVALID'], 'details': {}}
    expected = int((end - start).total_seconds() // 60)
    for sym in ALL26_SYMBOLS:
        rows = _read_csv_rows(candle_1m_path(sym))
        times = [_parse_iso(r.get('timestamp')) for r in rows]
        times = [x for x in times if x]
        gaps = sum((max(0, int((b - a).total_seconds() // 60) - 1) for a, b in zip(times, times[1:])))
        reverse = sum((1 for a, b in zip(times, times[1:]) if b <= a))
        future = sum((1 for x in times if x > end))
        bad_ohlcv = sum((1 for r in rows if any((str(r.get(k, '')) == '' for k in ('open', 'high', 'low', 'close', 'volume')))))
        bad_amount = sum((1 for r in rows if str(r.get('estimated_trade_value', '')) == ''))
        minute_ok = bool(len(rows) == expected and times and (times[0] == start + timedelta(minutes=1)) and (times[-1] == end) and (len(times) == len(set(times))) and (gaps == 0) and (reverse == 0) and (future == 0) and (bad_ohlcv == 0) and (bad_amount == 0))
        if not minute_ok:
            failures.append(f'{sym}:MINUTE rows={len(rows)} gaps={gaps} duplicate={len(times) - len(set(times))} reverse={reverse} future={future} ohlcv_missing={bad_ohlcv} trade_value_missing={bad_amount}')
        orderbook_ok = bool(os.path.isfile(orderbook_path(sym)) and _read_csv_rows(orderbook_path(sym)))
        if not orderbook_ok:
            failures.append(f'{sym}:ORDERBOOK')
        trades_ok = bool(os.path.isfile(trades_path(sym)) and _read_csv_rows(trades_path(sym)))
        if not trades_ok:
            failures.append(f'{sym}:TRADES')
        snapshots = _read_csv_rows(price_snapshot_path(sym))
        snapshot_ok = bool(snapshots)
        if not snapshots:
            failures.append(f'{sym}:SNAPSHOT')
        elif any((str(snapshots[-1].get(k, '')) == '' for k in ('requested_at', 'received_at', 'saved_at', 'latency_ms', 'timestamp', 'last_price'))):
            snapshot_ok = False
            failures.append(f'{sym}:SNAPSHOT_FIELDS')
        daily_ok = bool(os.path.isfile(candle_daily_path(sym)) and _read_csv_rows(candle_daily_path(sym)))
        if not daily_ok:
            failures.append(f'{sym}:DAILY')
        metadata = _read_csv_rows(stock_metadata_path(sym)) if os.path.isfile(stock_metadata_path(sym)) else []
        metadata_ok = bool(metadata) and all((str(metadata[-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http')))
        if not metadata:
            failures.append(f'{sym}:METADATA')
        elif not metadata_ok:
            failures.append(f'{sym}:METADATA_HTTP')
        ok = bool(minute_ok and orderbook_ok and trades_ok and snapshot_ok and daily_ok and metadata_ok)
        details[sym] = {'rows': len(rows), 'first': times[0].isoformat() if times else '', 'last': times[-1].isoformat() if times else '', 'gaps': gaps, 'duplicate': len(times) - len(set(times)), 'reverse': reverse, 'future': future, 'ohlcv_missing': bad_ohlcv, 'trade_value_missing': bad_amount, 'minute_ok': minute_ok, 'orderbook_ok': orderbook_ok, 'trades_ok': trades_ok, 'snapshot_ok': snapshot_ok, 'daily_ok': daily_ok, 'metadata_ok': metadata_ok, 'ok': ok}
    raw_path = os.path.join(raw_market_dir('KR'), f'api_{today()}.jsonl')
    if not os.path.isfile(raw_path) or os.path.getsize(raw_path) == 0:
        failures.append('RAW_API_RESPONSES_MISSING')
    if not _read_csv_rows(market_indicator_path()):
        failures.append('MARKET_INDICATORS_MISSING')
    if not _read_csv_rows(investor_trading_path()):
        failures.append('INVESTOR_TRADING_MISSING')
    missing_accounts = [x for x in MULTI_AI_IDS if not _read_csv_rows(multi_ai_path(x)) or not os.path.isfile(multi_ai_state_path(x))]
    if missing_accounts:
        failures.append('PAPER_ACCOUNTS_MISSING:' + ','.join(missing_accounts))
    return {'grade': 'GRADE_1' if not failures else 'GRADE_2_PARTIAL', 'failures': failures, 'details': details, 'paper_account_files': len(MULTI_AI_IDS) - len(missing_accounts)}

def _kr_backup_source_files(base):
    """한국 당일 원본만 백업 대상으로 고정한다.
    이전/복구/검증 ZIP과 drive_verify 다운로드본은 절대 다시 ZIP 안에 넣지 않는다.
    """
    out = []
    base_abs = os.path.abspath(base)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != 'drive_verify']
        for fn in files:
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, base)
            rel_norm = rel.replace(os.sep, '/')
            if rel_norm.startswith(('raw/US/', 'normalized/US/', 'us_trade_dates/', 'drive_verify/')):
                continue
            if fn.lower().endswith('.zip'):
                continue
            if '.BEFORE_RECOVERY' in fn or fn.endswith('.tmp'):
                continue
            if not os.path.isfile(fp):
                continue
            if not os.path.abspath(fp).startswith(base_abs + os.sep):
                continue
            out.append((rel_norm, fp))
    out.sort(key=lambda x: x[0])
    return out

def _verify_local_kr_backup_or_raise(path, trade_date):
    """로컬 ZIP을 실제로 다시 열어 GRADE_1이 아니면 성공본으로 교체하지 않는다."""
    report = inspect_downloaded_kr_backup_zip(path, trade_date)
    if report.get('grade') != 'GRADE_1':
        failures = report.get('failures', [])
        raise RuntimeError('로컬 백업 재검증 실패: ' + ' | '.join(map(str, failures[:12]))[:1400])
    return report

def _create_backup_zip_unlocked():
    """한국 1등급 검사 → 원본만 ZIP → CRC/내부검증 → 원자적 교체."""
    finalize_all_paper_accounts()
    repair_failures = []
    backfill_ok = False
    backfill_failures = []
    quality = {'grade': 'FAILED', 'failures': ['NOT_CHECKED'], 'details': {}}
    for grade1_pass in range(1, 6):
        pass_repair_failures = repair_kr_required_files_before_backup()
        repair_failures.extend([f'PASS_{grade1_pass}:{x}' for x in pass_repair_failures])
        pass_ok, pass_failures = finalize_kr_candles_grade1()
        quality = audit_kr_grade1()
        backfill_ok = pass_ok and quality.get('grade') == 'GRADE_1'
        backfill_failures.extend([f'PASS_{grade1_pass}:{x}' for x in pass_failures])
        if backfill_ok:
            break
        # 401은 같은 자격증명으로 5회 전체 복구를 반복해도 해결되지 않는다.
        # RAW 원본은 이미 별도 ZIP으로 보존했으므로 정식 GRADE_1 생성만 빠르게 실패 처리한다.
        auth_failed = any('HTTP_401' in str(x) for x in (pass_repair_failures + pass_failures))
        if auth_failed:
            break
        time.sleep(min(grade1_pass * 2, 5))
    quality['repair_failures'] = repair_failures
    quality['backfill_ok'] = backfill_ok
    quality['backfill_failures'] = backfill_failures
    S.setdefault('market_data_capture', {})['final_grade'] = quality.get('grade')
    S.setdefault('market_data_capture', {})['final_grade_failures'] = quality.get('failures', [])
    quality_path = os.path.join(market_data_dir(), f'grade1_report_{today()}.json')
    with open(quality_path, 'w', encoding='utf-8') as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)
    if not backfill_ok or quality.get('grade') != 'GRADE_1':
        raise RuntimeError('한국 백업 품질검사 미통과: ' + ' | '.join(map(str, quality.get('failures', [])[:12]))[:1400])
    base = day_dir()
    source_files = _kr_backup_source_files(base)
    path = backup_zip_path()
    tmp_path = os.path.join(os.path.dirname(path), f'.backup_KR_{today()}_{uuid.uuid4().hex}.tmp.zip')
    included_files = len(source_files)
    included_bytes = sum((os.path.getsize(fp) for _, fp in source_files))
    manifest = {'created_at_kst': now_text(), 'version': OPERATING_VERSION, 'toss_openapi_spec_version': TOSS_OPENAPI_SPEC_VERSION, 'toss_openapi_spec_url': TOSS_OPENAPI_SPEC_URL, 'kr_log_date': today(), 'included_files': included_files, 'uncompressed_bytes': included_bytes, 'market_mode': MARKET_MODE, 'kr_symbol_count': len(ALL26_SYMBOLS), 'kr_symbols': ALL26_SYMBOLS, 'us_data_included': False, 'data_quality_grade': quality.get('grade'), 'data_quality_failures': quality.get('failures', [])[:100], 'paper_account_files': quality.get('paper_account_files', 0), 'paper_only_mode': PAPER_ONLY_MODE, 'real_order_enabled': ENABLE_REAL_ORDER, 'real_auto_buy': ENABLE_REAL_AUTO_BUY, 'real_auto_sell': ENABLE_REAL_AUTO_SELL, 'nested_zip_excluded': True, 'drive_verify_excluded': True}
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for arc, fp in source_files:
                z.write(fp, arc)
            z.writestr('backup_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        local_report = _verify_local_kr_backup_or_raise(tmp_path, today())
        os.replace(tmp_path, path)
        with LOCK:
            S.setdefault('market_data_capture', {})['local_backup_verify'] = {'checked_at': now_text(), 'grade': local_report.get('grade', 'FAILED'), 'file': os.path.basename(path), 'size': os.path.getsize(path), 'included_files': included_files, 'uncompressed_bytes': included_bytes}
        return path
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def create_backup_zip():
    """한국 백업 공통 진입점.
    정식 GRADE_1 검사보다 먼저 당일 실제 원본 RAW 구조백업을 반드시 남긴다.
    검증/API/토큰이 실패해도 원본 복구 ZIP은 유지하며 가짜 행은 만들지 않는다.
    """
    with BACKUP_LOCK:
        rescue_error = ''
        try:
            create_kr_raw_rescue_backup(today())
        except Exception as e:
            rescue_error = str(e)[:500]
            with LOCK:
                S.setdefault('market_data_capture', {})['raw_rescue_error'] = rescue_error
        try:
            return _create_backup_zip_unlocked()
        except Exception:
            # 정식 백업 실패와 RAW 보존 실패를 혼동하지 않도록 상태만 남기고 원 예외를 유지한다.
            if rescue_error:
                set_error('KR RAW 구조백업도 실패: ' + rescue_error)
            raise


def kr_rescue_backup_path(trade_date=None):
    trade_date = trade_date or today()
    os.makedirs(os.path.join(BACKUP_ROOT, 'KR'), exist_ok=True)
    return os.path.join(BACKUP_ROOT, 'KR', f'backup_KR_RAW_RESCUE_{trade_date}.zip')


def create_kr_raw_rescue_backup(trade_date=None):
    """GRADE 판정과 무관하게 당일 실제 수집 원본을 먼저 보존한다.
    가짜 행 생성/가격 수정/CSV 재작성은 하지 않는다. ZIP CRC만 확인한다.
    이 파일은 분석용 GRADE_1 성공본이 아니라 복구용 원본 사본이다.
    """
    trade_date = trade_date or today()
    base = day_dir()
    source_files = _kr_backup_source_files(base)
    if not source_files:
        raise RuntimeError('KR RAW RESCUE: 당일 원본 파일이 없습니다.')
    path = kr_rescue_backup_path(trade_date)
    tmp_path = os.path.join(os.path.dirname(path), f'.backup_KR_RAW_RESCUE_{trade_date}_{uuid.uuid4().hex}.tmp.zip')
    manifest = {
        'created_at_kst': now_text(),
        'version': OPERATING_VERSION,
        'market': 'KR',
        'trade_date': trade_date,
        'recovery_mode': 'RAW_RESCUE_NO_GRADE_GATE',
        'source_files_preserved_as_is': True,
        'synthetic_rows_added': False,
        'prices_modified': False,
        'included_files': len(source_files),
        'uncompressed_bytes': sum(os.path.getsize(fp) for _, fp in source_files),
        'paper_only_mode': PAPER_ONLY_MODE,
        'real_order_enabled': ENABLE_REAL_ORDER,
    }
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for arc, fp in source_files:
                z.write(fp, arc)
            z.writestr('raw_rescue_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(tmp_path, 'r') as z:
            bad = z.testzip()
            if bad:
                raise RuntimeError(f'KR RAW RESCUE CRC 실패: {bad}')
        os.replace(tmp_path, path)
        with LOCK:
            S.setdefault('market_data_capture', {})['raw_rescue_backup'] = {
                'created_at': now_text(), 'file': os.path.basename(path),
                'size': os.path.getsize(path), 'included_files': len(source_files), 'crc_ok': True
            }
        save_state()
        return path
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def preserve_kr_raw_before_grade_check():
    """장 종료 백업 시 GRADE 검사보다 먼저 RAW 복구 ZIP을 보존한다."""
    with BACKUP_LOCK:
        return create_kr_raw_rescue_backup(today())


def google_drive_credentials_ready(require_refresh=True):
    basic = bool(GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET and GOOGLE_DRIVE_FOLDER_ID and GOOGLE_DRIVE_REDIRECT_URI)
    return basic and (bool(GOOGLE_DRIVE_REFRESH_TOKEN) if require_refresh else True)

def google_drive_oauth_start_url():
    """최초 1회 Google 승인을 위한 URL을 만든다. 토큰은 로그에 남기지 않는다."""
    global GOOGLE_OAUTH_STATE, GOOGLE_OAUTH_STATE_EXPIRES_AT
    if not google_drive_credentials_ready(require_refresh=False):
        raise RuntimeError('Google Drive OAuth 기본 환경변수가 설정되지 않았습니다.')
    with LOCK:
        GOOGLE_OAUTH_STATE = uuid.uuid4().hex + uuid.uuid4().hex
        GOOGLE_OAUTH_STATE_EXPIRES_AT = time.time() + 600
        state = GOOGLE_OAUTH_STATE
    params = {'client_id': GOOGLE_DRIVE_CLIENT_ID, 'redirect_uri': GOOGLE_DRIVE_REDIRECT_URI, 'response_type': 'code', 'scope': GOOGLE_DRIVE_SCOPE, 'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'true', 'state': state}
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)

def google_drive_exchange_oauth_code(qs):
    """OAuth callback 코드를 refresh token으로 교환한다. 반환 토큰은 사용자가 Render에 직접 저장한다."""
    global GOOGLE_OAUTH_STATE, GOOGLE_OAUTH_STATE_EXPIRES_AT
    if qs.get('error'):
        raise RuntimeError('Google 승인 실패: ' + str(qs.get('error', [''])[0]))
    code = str(qs.get('code', [''])[0])
    state = str(qs.get('state', [''])[0])
    with LOCK:
        expected = GOOGLE_OAUTH_STATE
        expires_at = GOOGLE_OAUTH_STATE_EXPIRES_AT
        GOOGLE_OAUTH_STATE = ''
        GOOGLE_OAUTH_STATE_EXPIRES_AT = 0.0
    if not code:
        raise RuntimeError('Google authorization code가 없습니다.')
    if not expected or state != expected or time.time() > expires_at:
        raise RuntimeError('OAuth state가 일치하지 않거나 10분이 지났습니다. 처음부터 다시 승인하세요.')
    r = requests.post('https://oauth2.googleapis.com/token', data={'code': code, 'client_id': GOOGLE_DRIVE_CLIENT_ID, 'client_secret': GOOGLE_DRIVE_CLIENT_SECRET, 'redirect_uri': GOOGLE_DRIVE_REDIRECT_URI, 'grant_type': 'authorization_code'}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'Google token 교환 실패 HTTP {r.status_code}: {r.text[:300]}')
    data = r.json()
    refresh_token = str(data.get('refresh_token', '')).strip()
    if not refresh_token:
        raise RuntimeError('refresh token이 발급되지 않았습니다. Google 권한을 취소한 뒤 prompt=consent로 다시 승인하세요.')
    return refresh_token

def _google_drive_auth_error_kind(status_code, body):
    body_text = str(body or '')
    low = body_text.lower()
    if int(status_code or 0) == 400 and 'invalid_grant' in low:
        return 'AUTH_REQUIRED'
    if 'expired or revoked' in low:
        return 'AUTH_REQUIRED'
    return 'TOKEN_REFRESH_FAILED'

def google_drive_access_token():
    if not google_drive_credentials_ready(require_refresh=True):
        raise RuntimeError('GOOGLE_DRIVE_REFRESH_TOKEN을 포함한 Drive 환경변수가 아직 완성되지 않았습니다.')
    r = requests.post('https://oauth2.googleapis.com/token', data={'client_id': GOOGLE_DRIVE_CLIENT_ID, 'client_secret': GOOGLE_DRIVE_CLIENT_SECRET, 'refresh_token': GOOGLE_DRIVE_REFRESH_TOKEN, 'grant_type': 'refresh_token'}, timeout=30)
    if r.status_code != 200:
        kind = _google_drive_auth_error_kind(r.status_code, r.text)
        with LOCK:
            S.setdefault('google_drive', {}).update({'status': kind, 'last_attempt_at': now_text(), 'last_error': f'HTTP {r.status_code}: {r.text[:500]}', 'reauth_url': f'{APP_URL}/google/oauth/start' if APP_URL else '/google/oauth/start'})
        save_state()
        if kind == 'AUTH_REQUIRED':
            raise RuntimeError(f'Google Drive 인증 재승인 필요: refresh token이 만료/취소되었습니다. {APP_URL}/google/oauth/start')
        raise RuntimeError(f'Google access token 갱신 실패 HTTP {r.status_code}: {r.text[:300]}')
    token = str(r.json().get('access_token', '')).strip()
    if not token:
        raise RuntimeError('Google access token 응답이 비어 있습니다.')
    return token

def validate_backup_zip_for_drive(path):
    if not os.path.isfile(path):
        raise RuntimeError('업로드할 ZIP 파일이 없습니다.')
    if os.path.getsize(path) <= 0:
        raise RuntimeError('업로드할 ZIP 파일 크기가 0입니다.')
    with zipfile.ZipFile(path, 'r') as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f'ZIP 무결성 검사 실패: {bad}')
        if 'backup_manifest.json' not in z.namelist():
            raise RuntimeError('backup_manifest.json이 ZIP에 없습니다.')

def file_md5(path):
    digest = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def google_drive_folder_snapshot(access_token):
    """대상 폴더의 기존 파일 ID·이름·크기·MD5를 읽기 전용으로 스냅샷한다."""
    files = []
    page_token = None
    while True:
        params = {'q': f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false", 'fields': 'nextPageToken,files(id,name,size,md5Checksum,modifiedTime,parents,trashed)', 'pageSize': 1000}
        if page_token:
            params['pageToken'] = page_token
        r = requests.get('https://www.googleapis.com/drive/v3/files', headers={'Authorization': f'Bearer {access_token}'}, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f'Drive 기존 파일 보호 스냅샷 실패 HTTP {r.status_code}: {r.text[:300]}')
        payload = r.json()
        files.extend(payload.get('files', []))
        page_token = payload.get('nextPageToken')
        if not page_token:
            break
    return {str(item.get('id')): {'name': str(item.get('name', '')), 'size': str(item.get('size', '')), 'md5Checksum': str(item.get('md5Checksum', '')), 'modifiedTime': str(item.get('modifiedTime', '')), 'parents': tuple(sorted(item.get('parents', []) or [])), 'trashed': bool(item.get('trashed', False))} for item in files if item.get('id')}

def verify_drive_existing_files_unchanged(before_snapshot, after_snapshot, new_file_id):
    """새로 만든 파일을 제외한 기존 파일이 그대로인지 강제 검증한다."""
    if not GOOGLE_DRIVE_VERIFY_EXISTING_UNCHANGED:
        return
    missing = []
    changed = []
    for file_id, before in before_snapshot.items():
        if file_id == new_file_id:
            continue
        after = after_snapshot.get(file_id)
        if after is None:
            missing.append(file_id)
            continue
        if before != after:
            changed.append({'id': file_id, 'before': before, 'after': after})
    if missing or changed:
        raise RuntimeError(f'Drive 기존 파일 불변성 검증 실패: missing={missing[:10]}, changed={changed[:3]}')

def google_drive_find_file(access_token, filename):
    escaped = filename.replace('\\', '\\\\').replace("'", "\\'")
    q = f"name = '{escaped}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
    r = requests.get('https://www.googleapis.com/drive/v3/files', headers={'Authorization': f'Bearer {access_token}'}, params={'q': q, 'fields': 'files(id,name,size,md5Checksum,webViewLink)', 'pageSize': 10}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'Drive 중복 파일 조회 실패 HTTP {r.status_code}: {r.text[:300]}')
    files = r.json().get('files', [])
    return files[0] if files else None

def google_drive_download_file(access_token, file_meta, destination_path):
    """Drive 파일을 읽기 전용 alt=media 방식으로 다운로드하고 크기·MD5를 검증한다."""
    file_id = str((file_meta or {}).get('id', '')).strip()
    if not file_id:
        raise RuntimeError('다운로드할 Drive 파일 ID가 없습니다.')
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    h = hashlib.md5()
    total = 0
    with requests.get(f"https://www.googleapis.com/drive/v3/files/{quote(file_id, safe='')}", headers={'Authorization': f'Bearer {access_token}'}, params={'alt': 'media'}, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise RuntimeError(f'Drive 백업 다운로드 실패 HTTP {r.status_code}: {r.text[:300]}')
        with open(destination_path, 'wb') as out:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                out.write(chunk)
                h.update(chunk)
                total += len(chunk)
    expected_size = int(to_float(file_meta.get('size', 0), 0))
    expected_md5 = str(file_meta.get('md5Checksum', '') or '').lower()
    if expected_size and total != expected_size:
        raise RuntimeError(f'Drive 다운로드 크기 불일치 expected={expected_size} actual={total}')
    if expected_md5 and h.hexdigest().lower() != expected_md5:
        raise RuntimeError(f'Drive 다운로드 MD5 불일치 expected={expected_md5} actual={h.hexdigest()}')
    return {'bytes': total, 'md5': h.hexdigest()}

def _zip_read_csv(z, member):
    if not member:
        return []
    with z.open(member, 'r') as raw:
        text = io.TextIOWrapper(raw, encoding='utf-8-sig', errors='replace', newline='')
        return list(csv.DictReader(text))

def inspect_downloaded_kr_backup_zip(path, expected_date=None):
    """Drive 다운로드 ZIP을 독립적으로 열어 한국시장 엄격 1등급 조건을 검사한다."""
    expected_date = expected_date or today()
    failures = []
    warnings = []
    details = {}
    result = {'checked_at_kst': now_text(), 'file': os.path.basename(path), 'trade_date': expected_date, 'grade': 'FAILED', 'failures': failures, 'warnings': warnings, 'symbol_count': 0, 'paper_csv_count': 0, 'paper_state_count': 0, 'crc_ok': False, 'manifest_ok': False, 'paper_only_ok': False, 'zip_member_count': 0, 'details': details}
    if not os.path.isfile(path):
        failures.append('ZIP_FILE_MISSING')
        return result

    def add_failure(text):
        if text not in failures:
            failures.append(text)

    def members_by_basename(names, basename):
        return [n for n in names if not n.replace('\\', '/').endswith('/') and os.path.basename(n.replace('\\', '/')) == basename]

    def one_member(names, basename, label):
        found = members_by_basename(names, basename)
        if len(found) == 0:
            add_failure(f'{label}_MISSING:{basename}')
            return ''
        if len(found) > 1:
            add_failure(f'{label}_DUPLICATE:{basename}:{len(found)}')
            return ''
        return found[0]

    def nonblank(row, keys):
        return all((str(row.get(k, '')).strip() != '' for k in keys))

    def finite_number(value):
        try:
            v = float(str(value).replace(',', '').strip())
            return v == v and v not in (float('inf'), float('-inf'))
        except Exception:
            return False

    def csv_timestamp_health(rows, key):
        parsed = [_parse_iso(r.get(key)) for r in rows]
        valid = [KST.localize(x) if x.tzinfo is None else x.astimezone(KST) for x in parsed if x]
        invalid = len(rows) - len(valid)
        reverse = sum((1 for a, b in zip(valid, valid[1:]) if b < a))
        duplicate = len(valid) - len(set(valid))
        wrong_day = sum((1 for x in valid if x.date().isoformat() != expected_date))
        return (valid, invalid, reverse, duplicate, wrong_day)
    try:
        with zipfile.ZipFile(path, 'r') as z:
            bad = z.testzip()
            if bad:
                add_failure(f'ZIP_CRC_FAILED:{bad}')
                return result
            result['crc_ok'] = True
            names = [n for n in z.namelist() if not n.replace('\\', '/').endswith('/')]
            result['zip_member_count'] = len(names)
            if len(names) != len(set(names)):
                add_failure('ZIP_DUPLICATE_MEMBER_NAMES')
            manifest_member = one_member(names, 'backup_manifest.json', 'BACKUP_MANIFEST')
            manifest = {}
            if manifest_member:
                try:
                    manifest = json.loads(z.read(manifest_member).decode('utf-8-sig'))
                    if not isinstance(manifest, dict):
                        raise ValueError('manifest is not object')
                except Exception as e:
                    add_failure(f'BACKUP_MANIFEST_INVALID:{str(e)[:120]}')
                    manifest = {}
            if manifest:
                manifest_date = str(manifest.get('kr_log_date') or manifest.get('trade_date') or '')
                manifest_symbols = [str(x) for x in manifest.get('kr_symbols') or []]
                manifest_count = int(to_float(manifest.get('kr_symbol_count', 0), 0))
                included_files = int(to_float(manifest.get('included_files', -1), -1))
                if manifest_date != expected_date:
                    add_failure(f'MANIFEST_DATE_MISMATCH:{manifest_date}')
                if manifest_count != len(ALL26_SYMBOLS):
                    add_failure(f'MANIFEST_SYMBOL_COUNT:{manifest_count}')
                if set(manifest_symbols) != set(ALL26_SYMBOLS) or len(manifest_symbols) != len(ALL26_SYMBOLS):
                    add_failure('MANIFEST_SYMBOL_LIST_MISMATCH')
                if included_files != len(names) - 1:
                    add_failure(f'MANIFEST_INCLUDED_FILES_MISMATCH:{included_files}!={len(names) - 1}')
                if str(manifest.get('data_quality_grade', '')) != 'GRADE_1':
                    add_failure(f"MANIFEST_GRADE_NOT_1:{manifest.get('data_quality_grade')}")
                if list(manifest.get('data_quality_failures') or []):
                    add_failure('MANIFEST_HAS_QUALITY_FAILURES')
                if int(to_float(manifest.get('paper_account_files', 0), 0)) != len(MULTI_AI_IDS):
                    add_failure(f"MANIFEST_PAPER_ACCOUNT_COUNT:{manifest.get('paper_account_files')}")
                safety_ok = manifest.get('paper_only_mode') is True and manifest.get('real_order_enabled') is False and (manifest.get('real_auto_buy') is False) and (manifest.get('real_auto_sell') is False)
                result['paper_only_ok'] = safety_ok
                if not safety_ok:
                    add_failure('MANIFEST_REAL_ORDER_SAFETY_FAILED')
                result['manifest_ok'] = not any((x.startswith('MANIFEST_') or x.startswith('BACKUP_MANIFEST') for x in failures))
            expected_times = [KST.localize(datetime.strptime(expected_date + ' 09:01', '%Y-%m-%d %H:%M')) + timedelta(minutes=i) for i in range(390)]
            expected_iso = [x.isoformat() for x in expected_times]
            passed_symbols = 0
            for sym in ALL26_SYMBOLS:
                candle_member = one_member(names, os.path.basename(candle_1m_path(sym)), f'{sym}:MINUTE')
                orderbook_member = one_member(names, os.path.basename(orderbook_path(sym)), f'{sym}:ORDERBOOK')
                trades_member = one_member(names, os.path.basename(trades_path(sym)), f'{sym}:TRADES')
                snapshot_member = one_member(names, os.path.basename(price_snapshot_path(sym)), f'{sym}:SNAPSHOT')
                daily_member = one_member(names, os.path.basename(candle_daily_path(sym)), f'{sym}:DAILY')
                metadata_member = one_member(names, os.path.basename(stock_metadata_path(sym)), f'{sym}:METADATA')
                rows = _zip_read_csv(z, candle_member)
                times, ts_invalid, reverse, duplicate, wrong_day = csv_timestamp_health(rows, 'timestamp')
                actual_iso = [x.isoformat() for x in times]
                bad_ohlcv = 0
                bad_symbol = 0
                bad_price_relation = 0
                for r in rows:
                    if str(r.get('symbol', '')) != sym:
                        bad_symbol += 1
                    if not nonblank(r, ('open', 'high', 'low', 'close', 'volume')) or not all((finite_number(r.get(k)) for k in ('open', 'high', 'low', 'close', 'volume'))):
                        bad_ohlcv += 1
                        continue
                    o, h, l, c, v = (float(r[k]) for k in ('open', 'high', 'low', 'close', 'volume'))
                    if h < max(o, l, c) or l > min(o, h, c) or v < 0:
                        bad_price_relation += 1
                minute_ok = len(rows) == 390 and actual_iso == expected_iso and (ts_invalid == 0) and (reverse == 0) and (duplicate == 0) and (wrong_day == 0) and (bad_ohlcv == 0) and (bad_symbol == 0) and (bad_price_relation == 0)
                orderbook_rows = _zip_read_csv(z, orderbook_member)
                ob_times, ob_invalid, ob_reverse, _, ob_wrong_day = csv_timestamp_health(orderbook_rows, 'saved_at')
                orderbook_bad = sum((1 for r in orderbook_rows if str(r.get('symbol', '')) != sym or not nonblank(r, ('best_ask', 'best_bid', 'asks_json', 'bids_json'))))
                # ORDERBOOK/SNAPSHOT은 호출 주기형 보조 스트림이다. 1분봉처럼 고정 행 수를 강제하지 않는다.
                # 백업의 목적은 수집된 원본 보존이므로, 한 행 이상 존재하면 백업 자체는 허용하고
                # timestamp/순서/필드 이상은 경고로 남겨 데이터 분석 시 제외 판단할 수 있게 한다.
                orderbook_ok = len(orderbook_rows) > 0
                if orderbook_ok and (ob_invalid or ob_reverse or ob_wrong_day or orderbook_bad):
                    warnings.append(f'{sym}:ORDERBOOK_WARNING rows={len(orderbook_rows)} invalid_ts={ob_invalid} reverse={ob_reverse} wrong_day={ob_wrong_day} bad={orderbook_bad}')
                trade_rows = _zip_read_csv(z, trades_member)
                tr_times, tr_invalid, tr_reverse, _, tr_wrong_day = csv_timestamp_health(trade_rows, 'timestamp')
                trade_bad = sum((1 for r in trade_rows if str(r.get('symbol', '')) != sym or not nonblank(r, ('price', 'volume')) or (not finite_number(r.get('price'))) or (not finite_number(r.get('volume')))))
                trades_ok = len(trade_rows) > 0 and tr_invalid == 0 and (tr_reverse == 0) and (tr_wrong_day == 0) and (trade_bad == 0)
                snapshot_rows = _zip_read_csv(z, snapshot_member)
                sp_times, sp_invalid, sp_reverse, _, sp_wrong_day = csv_timestamp_health(snapshot_rows, 'saved_at')
                snapshot_bad = sum((1 for r in snapshot_rows if str(r.get('symbol', '')) != sym or not nonblank(r, ('last_price',)) or (not finite_number(r.get('last_price')))))
                snapshot_ok = len(snapshot_rows) > 0
                if snapshot_ok and (sp_invalid or sp_reverse or sp_wrong_day or snapshot_bad):
                    warnings.append(f'{sym}:SNAPSHOT_WARNING rows={len(snapshot_rows)} invalid_ts={sp_invalid} reverse={sp_reverse} wrong_day={sp_wrong_day} bad={snapshot_bad}')
                daily_rows = _zip_read_csv(z, daily_member)
                daily_bad = sum((1 for r in daily_rows if str(r.get('symbol', '')) != sym or not nonblank(r, ('timestamp', 'open', 'high', 'low', 'close', 'volume'))))
                daily_ok = len(daily_rows) > 0 and daily_bad == 0
                metadata_rows = _zip_read_csv(z, metadata_member)
                metadata_http_ok = bool(metadata_rows) and all((str(metadata_rows[-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http')))
                metadata_ok = metadata_http_ok and str(metadata_rows[-1].get('symbol', '')) == sym
                sym_ok = minute_ok and orderbook_ok and trades_ok and snapshot_ok and daily_ok and metadata_ok
                if sym_ok:
                    passed_symbols += 1
                else:
                    if not minute_ok:
                        add_failure(f'{sym}:MINUTE_INVALID rows={len(rows)} ts_invalid={ts_invalid} reverse={reverse} duplicate={duplicate} wrong_day={wrong_day} ohlcv={bad_ohlcv} symbol={bad_symbol} relation={bad_price_relation}')
                    if not orderbook_ok:
                        add_failure(f'{sym}:ORDERBOOK_MISSING rows={len(orderbook_rows)}')
                    if not trades_ok:
                        add_failure(f'{sym}:TRADES_INVALID rows={len(trade_rows)} invalid_ts={tr_invalid} reverse={tr_reverse} wrong_day={tr_wrong_day} bad={trade_bad}')
                    if not snapshot_ok:
                        add_failure(f'{sym}:SNAPSHOT_MISSING rows={len(snapshot_rows)}')
                    if not daily_ok:
                        add_failure(f'{sym}:DAILY_INVALID rows={len(daily_rows)} bad={daily_bad}')
                    if not metadata_ok:
                        add_failure(f'{sym}:METADATA_INVALID rows={len(metadata_rows)} http_ok={metadata_http_ok}')
                details[sym] = {'ok': sym_ok, 'minute_rows': len(rows), 'first': actual_iso[0] if actual_iso else '', 'last': actual_iso[-1] if actual_iso else '', 'minute_invalid_timestamp': ts_invalid, 'minute_reverse': reverse, 'minute_duplicate': duplicate, 'minute_wrong_day': wrong_day, 'ohlcv_invalid': bad_ohlcv, 'symbol_mismatch': bad_symbol, 'ohlc_relation_invalid': bad_price_relation, 'orderbook_rows': len(orderbook_rows), 'orderbook_ok': orderbook_ok, 'trade_rows': len(trade_rows), 'trades_ok': trades_ok, 'snapshot_rows': len(snapshot_rows), 'snapshot_ok': snapshot_ok, 'daily_rows': len(daily_rows), 'daily_ok': daily_ok, 'metadata_http_ok': metadata_http_ok}
            result['symbol_count'] = passed_symbols
            paper_csv_count = 0
            paper_state_count = 0
            for account_id in MULTI_AI_IDS:
                csv_member = one_member(names, os.path.basename(multi_ai_path(account_id)), f'PAPER_CSV:{account_id}')
                state_member = one_member(names, os.path.basename(multi_ai_state_path(account_id)), f'PAPER_STATE:{account_id}')
                csv_rows = _zip_read_csv(z, csv_member)
                if csv_member and csv_rows:
                    paper_csv_count += 1
                else:
                    add_failure(f'PAPER_CSV_INVALID:{account_id}')
                if state_member:
                    try:
                        state_obj = json.loads(z.read(state_member).decode('utf-8-sig'))
                        if isinstance(state_obj, dict):
                            paper_state_count += 1
                        else:
                            add_failure(f'PAPER_STATE_INVALID:{account_id}')
                    except Exception:
                        add_failure(f'PAPER_STATE_INVALID:{account_id}')
            result['paper_csv_count'] = paper_csv_count
            result['paper_state_count'] = paper_state_count
            if paper_csv_count != len(MULTI_AI_IDS) or paper_state_count != len(MULTI_AI_IDS):
                add_failure(f'PAPER_ACCOUNT_COUNT csv={paper_csv_count} state={paper_state_count} expected={len(MULTI_AI_IDS)}')
    except zipfile.BadZipFile:
        add_failure('ZIP_OPEN_FAILED:BAD_ZIP')
    except Exception as e:
        add_failure(f'ZIP_INSPECTION_ERROR:{str(e)[:300]}')
    result['grade'] = 'GRADE_1' if not failures else 'FAILED'
    return result

def verify_kr_backup_file_from_google_drive(file_meta, trade_date=None):
    """방금 업로드한 그 Drive 파일 ID를 직접 재다운로드해 한국 백업을 검증한다.
    동일 날짜의 과거 exact-name 파일을 잘못 집어 검증하는 문제를 막는다.
    """
    trade_date = trade_date or today()
    if not isinstance(file_meta, dict) or not str(file_meta.get('id', '')).strip():
        return (False, {'grade': 'FAILED', 'trade_date': trade_date, 'failures': ['DRIVE_UPLOADED_FILE_META_INVALID']})
    access_token = google_drive_access_token()
    verify_dir = os.path.join(LOG_ROOT, trade_date, 'drive_verify')
    os.makedirs(verify_dir, exist_ok=True)
    safe_name = os.path.basename(str(file_meta.get('name') or f'backup_{trade_date}.zip'))
    local_path = os.path.join(verify_dir, f"uploaded_{str(file_meta.get('id', ''))}_{safe_name}")
    download_meta = google_drive_download_file(access_token, file_meta, local_path)
    report = inspect_downloaded_kr_backup_zip(local_path, trade_date)
    report['drive_file_id'] = str(file_meta.get('id', ''))
    report['drive_file_name'] = str(file_meta.get('name', ''))
    report['drive_file_size'] = int(to_float(file_meta.get('size', 0), 0))
    report['drive_md5'] = str(file_meta.get('md5Checksum', ''))
    report['downloaded_bytes'] = download_meta.get('bytes', 0)
    report['downloaded_md5'] = download_meta.get('md5', '')
    report_path = os.path.join(verify_dir, f'drive_uploaded_grade1_report_{trade_date}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with LOCK:
        S['google_drive'].update({'verify_status': 'GRADE_1' if report.get('grade') == 'GRADE_1' else 'FAILED', 'verify_checked_at': now_text(), 'verify_file_name': report.get('drive_file_name', ''), 'verify_file_id': report.get('drive_file_id', ''), 'verify_report_path': report_path, 'verify_failures': report.get('failures', [])[:100]})
    return (report.get('grade') == 'GRADE_1', report)

def google_drive_find_us_backups(access_token, trade_date):
    """해당 미국 거래일의 기존 백업 후보를 최신순으로 읽기 전용 조회한다."""
    prefix = f'backup_US_{trade_date}'
    escaped = prefix.replace('\\', '\\\\').replace("'", "\\'")
    q = f"name contains '{escaped}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
    r = requests.get('https://www.googleapis.com/drive/v3/files', headers={'Authorization': f'Bearer {access_token}'}, params={'q': q, 'fields': 'files(id,name,size,md5Checksum,modifiedTime,webViewLink)', 'orderBy': 'modifiedTime desc', 'pageSize': 100}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'Drive 미국 백업 조회 실패 HTTP {r.status_code}: {r.text[:300]}')
    out = []
    for x in r.json().get('files', []):
        name = str(x.get('name', ''))
        if name.startswith(prefix) and name.endswith('.zip'):
            out.append(x)
    return out

def inspect_downloaded_us_backup_zip(path, expected_date):
    """Drive에서 다시 받은 미국 ZIP을 CRC·14종목·필수자료·원천결측까지 독립 검사한다."""
    failures = []
    result = {'checked_at_kst': now_text(), 'file': os.path.basename(path), 'trade_date': expected_date, 'grade': 'FAILED', 'failures': failures, 'crc_ok': False, 'manifest_ok': False, 'symbol_count': 0, 'verified_source_gap_count': 0, 'details': {}}
    if not os.path.isfile(path):
        failures.append('ZIP_FILE_MISSING')
        return result
    try:
        with zipfile.ZipFile(path, 'r') as z:
            bad = z.testzip()
            if bad:
                failures.append(f'ZIP_CRC_BAD:{bad}')
                return result
            result['crc_ok'] = True
            names = [n for n in z.namelist() if not n.replace('\\', '/').endswith('/')]
            if len(names) != len(set(names)):
                failures.append('ZIP_DUPLICATE_MEMBER_NAMES')
            manifest_names = [n for n in names if os.path.basename(n.replace('\\', '/')) == 'backup_manifest.json']
            if len(manifest_names) != 1:
                failures.append(f'BACKUP_MANIFEST_COUNT:{len(manifest_names)}')
                return result
            try:
                manifest = json.loads(z.read(manifest_names[0]).decode('utf-8-sig'))
            except Exception as e:
                failures.append(f'BACKUP_MANIFEST_PARSE:{e}')
                return result
            expected_symbols = [str(x).upper() for x in US_SYMBOLS]
            manifest_symbols = [str(x).upper() for x in manifest.get('symbols', [])] if isinstance(manifest.get('symbols'), list) else []
            if str(manifest.get('market', '')).upper() != 'US':
                failures.append('MANIFEST_MARKET_NOT_US')
            if str(manifest.get('trade_date', '')) != str(expected_date):
                failures.append('MANIFEST_TRADE_DATE_MISMATCH')
            if manifest_symbols != expected_symbols:
                failures.append('MANIFEST_SYMBOLS_MISMATCH')
            if manifest.get('paper_only_mode') is not True:
                failures.append('MANIFEST_PAPER_ONLY_FALSE')
            if manifest.get('real_order_enabled') is not False or manifest.get('real_auto_buy') is not False or manifest.get('real_auto_sell') is not False:
                failures.append('MANIFEST_REAL_ORDER_GUARD_FAIL')
            start = _parse_iso(manifest.get('regular_start'))
            end = _parse_iso(manifest.get('regular_end'))
            if not start or not end or int((end - start).total_seconds() // 60) != 390:
                failures.append('MANIFEST_US_SESSION_BOUNDARY_INVALID')
            result['manifest_ok'] = not any((x.startswith('MANIFEST_') for x in failures))
            verified_raw = manifest.get('verified_source_gaps', {}) or {}
            verified_map = {}
            if isinstance(verified_raw, dict):
                for sym, entries in verified_raw.items():
                    vals = set()
                    for item in entries if isinstance(entries, list) else []:
                        ts = item.get('timestamp') if isinstance(item, dict) else item
                        dt = _parse_iso(ts)
                        if dt:
                            vals.add(dt.replace(second=0, microsecond=0))
                    verified_map[str(sym).upper()] = vals

            def members_for_basename(base):
                return [n for n in names if os.path.basename(n.replace('\\', '/')) == base]
            for sym in expected_symbols:
                detail = {}
                required = {'candles': f'candles_1m_{sym}_{expected_date}.csv', 'prices': f'prices_{sym}_{expected_date}.csv', 'daily': f'candles_1d_{sym}_{expected_date}.csv', 'orderbook': f'orderbook_{sym}_{expected_date}.csv', 'trades': f'trades_{sym}_{expected_date}.csv', 'metadata': f'metadata_{sym}_{expected_date}.csv'}
                members = {}
                for kind, base in required.items():
                    hits = members_for_basename(base)
                    if len(hits) != 1:
                        failures.append(f'{sym}:{kind.upper()}_MEMBER_COUNT_{len(hits)}')
                        members[kind] = ''
                    else:
                        members[kind] = hits[0]
                if not members.get('candles'):
                    result['details'][sym] = detail
                    continue
                rows = _zip_read_csv(z, members['candles'])
                times = []
                bad_ohlcv = 0
                for row in rows:
                    dt = _parse_iso(row.get('timestamp'))
                    if dt:
                        times.append(dt.replace(second=0, microsecond=0))
                    if any((str(row.get(k, '')).strip() == '' for k in ('open', 'high', 'low', 'close', 'volume', 'estimated_trade_value'))):
                        bad_ohlcv += 1
                duplicate = len(times) - len(set(times))
                reverse = sum((1 for a, b in zip(times, times[1:]) if b <= a))
                allowed = verified_map.get(sym, set())
                missing = []
                future = 0
                if start and end:
                    expected_times = [start + timedelta(minutes=i) for i in range(390)]
                    have = set(times)
                    missing = [t for t in expected_times if t not in have]
                    future = sum((1 for t in times if t < start or t >= end))
                    boundary_ok = (start in have or start in allowed) and (end - timedelta(minutes=1) in have or end - timedelta(minutes=1) in allowed)
                else:
                    boundary_ok = False
                source_gap_ok = set(missing) == allowed
                expected_rows = 390 - len(allowed)
                if len(rows) != expected_rows or duplicate or reverse or future or bad_ohlcv or (not boundary_ok) or (not source_gap_ok):
                    failures.append(f'{sym}:CANDLES rows={len(rows)}/{expected_rows},missing={len(missing)},allowed={len(allowed)},dup={duplicate},reverse={reverse},outside={future},bad={bad_ohlcv}')
                for kind in ('prices', 'daily', 'orderbook', 'trades', 'metadata'):
                    member = members.get(kind)
                    if member and (not _zip_read_csv(z, member)):
                        failures.append(f'{sym}:{kind.upper()}_EMPTY')
                if members.get('metadata'):
                    meta_rows = _zip_read_csv(z, members['metadata'])
                    if not meta_rows or not all((str(meta_rows[-1].get(k, '')).strip() == '200' for k in ('stock_http', 'warning_http', 'limits_http'))):
                        failures.append(f'{sym}:METADATA_HTTP_INVALID')
                detail.update({'rows': len(rows), 'expected_rows': expected_rows, 'missing_minutes': [x.isoformat() for x in missing], 'verified_source_gaps': [x.isoformat() for x in sorted(allowed)], 'duplicate': duplicate, 'reverse': reverse, 'outside_session': future, 'bad_ohlcv': bad_ohlcv})
                result['details'][sym] = detail
            raw_base = f'api_{expected_date}.jsonl'
            raw_hits = members_for_basename(raw_base)
            if len(raw_hits) != 1:
                failures.append(f'RAW_API_MEMBER_COUNT:{len(raw_hits)}')
            else:
                info = z.getinfo(raw_hits[0])
                if info.file_size <= 0:
                    failures.append('RAW_API_RESPONSES_EMPTY')
            result['symbol_count'] = len(expected_symbols)
            result['verified_source_gap_count'] = sum((len(v) for v in verified_map.values()))
            result['grade'] = 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS' if not failures and result['verified_source_gap_count'] > 0 else 'GRADE_1' if not failures else 'FAILED'
            return result
    except zipfile.BadZipFile:
        failures.append('ZIP_OPEN_FAILED')
    except Exception as e:
        failures.append(f'US_ZIP_INSPECTION_ERROR:{e}')
    return result

def verify_us_backup_file_from_google_drive(file_meta, trade_date):
    """지정된 Drive 미국 ZIP을 재다운로드해 실제 내부자료까지 검증한다."""
    access_token = google_drive_access_token()
    with tempfile.TemporaryDirectory(prefix='us_drive_verify_') as td:
        path = os.path.join(td, str((file_meta or {}).get('name') or f'backup_US_{trade_date}.zip'))
        google_drive_download_file(access_token, file_meta, path)
        report = inspect_downloaded_us_backup_zip(path, trade_date)
    return (report.get('grade') in {'GRADE_1', 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS'}, report)

def find_verified_existing_us_backup_on_drive(trade_date):
    """로컬 state가 사라져도 Drive의 기존 정상 미국백업을 찾아 중복생성을 막는다."""
    access_token = google_drive_access_token()
    candidates = google_drive_find_us_backups(access_token, trade_date)
    checked = []
    for meta in candidates:
        try:
            ok, report = verify_us_backup_file_from_google_drive(meta, trade_date)
            checked.append({'id': meta.get('id', ''), 'name': meta.get('name', ''), 'ok': ok, 'failures': report.get('failures', [])[:10]})
            if ok:
                return (meta, report, checked)
        except Exception as e:
            checked.append({'id': meta.get('id', ''), 'name': meta.get('name', ''), 'ok': False, 'failures': [str(e)[:300]]})
    return (None, None, checked)

def google_drive_resumable_upload(path):
    """기존 Drive 파일을 절대 건드리지 않고 새 ZIP만 추가한다."""
    if not GOOGLE_DRIVE_APPEND_ONLY:
        raise RuntimeError('Drive APPEND_ONLY 보호가 꺼져 있어 업로드를 중단합니다.')
    if GOOGLE_DRIVE_ALLOW_DELETE or GOOGLE_DRIVE_ALLOW_UPDATE:
        raise RuntimeError('Drive 삭제/수정 허용 설정이 감지되어 업로드를 중단합니다.')
    validate_backup_zip_for_drive(path)
    access_token = google_drive_access_token()
    before_snapshot = google_drive_folder_snapshot(access_token)
    filename = os.path.basename(path)
    total = os.path.getsize(path)
    local_md5 = file_md5(path)
    existing = google_drive_find_file(access_token, filename)
    if existing and int(existing.get('size', -1)) == total and (str(existing.get('md5Checksum', '')) == local_md5):
        return existing
    upload_filename = filename
    if existing:
        stem, ext = os.path.splitext(filename)
        upload_filename = f"{stem}__{now_kst().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json; charset=UTF-8', 'X-Upload-Content-Type': 'application/zip', 'X-Upload-Content-Length': str(total)}
    init_url = 'https://www.googleapis.com/upload/drive/v3/files'
    init = requests.post(init_url, headers=headers, params={'uploadType': 'resumable', 'fields': 'id,name,size,md5Checksum,webViewLink'}, json={'name': upload_filename, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}, timeout=30)
    if init.status_code not in (200, 201):
        raise RuntimeError(f'Drive resumable 세션 생성 실패 HTTP {init.status_code}: {init.text[:300]}')
    session_url = init.headers.get('Location', '')
    if not session_url:
        raise RuntimeError('Drive resumable 업로드 Location 헤더가 없습니다.')
    final_response = None
    offset = 0
    with open(path, 'rb') as f:
        while offset < total:
            chunk = f.read(GOOGLE_DRIVE_CHUNK_BYTES)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            put = requests.put(session_url, headers={'Content-Length': str(len(chunk)), 'Content-Range': f'bytes {offset}-{end}/{total}', 'Content-Type': 'application/zip'}, data=chunk, timeout=180)
            if put.status_code == 308:
                offset = end + 1
                continue
            if put.status_code not in (200, 201):
                raise RuntimeError(f'Drive ZIP 전송 실패 HTTP {put.status_code}: {put.text[:300]}')
            final_response = put
            offset = end + 1
    if final_response is None or offset != total:
        raise RuntimeError(f'Drive ZIP 전송이 완료되지 않았습니다: {offset}/{total} bytes')
    uploaded = final_response.json()
    file_id = str(uploaded.get('id') or (existing or {}).get('id') or '')
    if not file_id:
        raise RuntimeError('업로드 응답에 Drive file ID가 없습니다.')
    verify = requests.get(f'https://www.googleapis.com/drive/v3/files/{file_id}', headers={'Authorization': f'Bearer {access_token}'}, params={'fields': 'id,name,size,md5Checksum,webViewLink'}, timeout=30)
    if verify.status_code != 200:
        raise RuntimeError(f'Drive 업로드 검증 실패 HTTP {verify.status_code}: {verify.text[:300]}')
    meta = verify.json()
    if int(meta.get('size', -1)) != total:
        raise RuntimeError(f"Drive 파일 크기 불일치: local={total}, drive={meta.get('size')}")
    if meta.get('md5Checksum') and str(meta.get('md5Checksum')) != local_md5:
        raise RuntimeError('Drive MD5 검증 불일치')
    after_snapshot = google_drive_folder_snapshot(access_token)
    verify_drive_existing_files_unchanged(before_snapshot, after_snapshot, str(meta.get('id', '')))
    return meta

def upload_backup_to_google_drive(path):
    with LOCK:
        S['google_drive'].update({'status': 'UPLOADING', 'last_attempt_at': now_text(), 'last_file_name': os.path.basename(path), 'last_error': '', 'retry_count': 0})
    last_error = ''
    for attempt, wait_sec in enumerate((0, 2, 5), start=1):
        if wait_sec:
            time.sleep(wait_sec)
        try:
            meta = google_drive_resumable_upload(path)
            with LOCK:
                S['google_drive'].update({'status': 'SUCCESS', 'last_success_at': now_text(), 'last_file_name': str(meta.get('name', os.path.basename(path))), 'last_file_id': str(meta.get('id', '')), 'last_file_size': int(meta.get('size', 0)), 'last_web_view_link': str(meta.get('webViewLink', '')), 'last_error': '', 'retry_count': attempt - 1})
            save_state()
            return (True, meta)
        except Exception as e:
            last_error = str(e)
            with LOCK:
                S['google_drive'].update({'status': 'RETRYING', 'last_error': last_error, 'retry_count': attempt})
    with LOCK:
        S['google_drive'].update({'status': 'FAILED', 'last_error': last_error})
    save_state()
    return (False, {'error': last_error})

def _us_expected_candle_times(start, end):
    count = int((end - start).total_seconds() // 60)
    return [start + timedelta(minutes=i) for i in range(count)]

def _us_candle_row_from_api(sym, c, req, rec, latency):
    ts = str(c.get('timestamp', ''))
    close = to_float(c.get('closePrice', 0))
    volume = to_float(c.get('volume', 0))
    return {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': ts, 'open': c.get('openPrice', 0), 'high': c.get('highPrice', 0), 'low': c.get('lowPrice', 0), 'close': c.get('closePrice', 0), 'volume': c.get('volume', 0), 'estimated_trade_value': round(close * volume, 4), 'currency': c.get('currency', 'USD')}

def _verify_us_source_gap(sym, target, cal, retries=3):
    """정확한 1분봉이 과거 API에도 없는지 검증한다. 가짜 봉은 절대 생성하지 않는다."""
    evidence = []
    wanted = target.replace(second=0, microsecond=0)
    before = (wanted + timedelta(minutes=2)).isoformat()
    for attempt in range(max(1, retries)):
        req = now_kst()
        t0 = time.time()
        code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': 10, 'before': before, 'adjusted': True}, timeout=12)
        rec = now_kst()
        latency = round((time.time() - t0) * 1000, 3)
        result = _result_dict(data)
        candles = result.get('candles', []) if code == 200 and isinstance(result, dict) else []
        seen = []
        exact = None
        for c in candles if isinstance(candles, list) else []:
            dt = _parse_iso(c.get('timestamp'))
            if not dt:
                continue
            minute = dt.replace(second=0, microsecond=0)
            seen.append(minute.isoformat())
            if minute == wanted:
                exact = _us_candle_row_from_api(sym, c, req, rec, latency)
                break
        evidence.append({'attempt': attempt + 1, 'http': code, 'seen': seen})
        if exact:
            return (exact, False, evidence)
        if attempt < retries - 1:
            time.sleep(min(1 + attempt, 2))
    prev = (wanted - timedelta(minutes=1)).isoformat()
    nxt = (wanted + timedelta(minutes=1)).isoformat()
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))

    def _gap_evidence_ok(e):
        if e.get('http') != 200 or wanted.isoformat() in e.get('seen', []):
            return False
        seen_times = e.get('seen', [])
        if start and wanted == start.replace(second=0, microsecond=0):
            return nxt in seen_times
        if end and wanted == (end - timedelta(minutes=1)).replace(second=0, microsecond=0):
            return prev in seen_times
        return prev in seen_times and nxt in seen_times
    verified = all((_gap_evidence_ok(e) for e in evidence))
    return (None, verified, evidence)

def finalize_us_candles_grade1():
    state = S.setdefault('us_market_data_capture', {})
    cal = state.get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))
    failures = []
    if not start or not end:
        return (False, ['US_CALENDAR_INVALID'])
    headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'estimated_trade_value', 'currency']
    verified_gaps = {}
    for sym in US_SYMBOLS:
        collected = {}
        for old in _read_csv_rows(us_data_path('candles_1m', sym)):
            ts = str(old.get('timestamp', ''))
            dt = _parse_iso(ts)
            if dt and start <= dt < end:
                collected[ts] = {h: old.get(h, '') for h in headers}
        before = end.isoformat()
        seen = set()
        for _ in range(4):
            if before in seen:
                break
            seen.add(before)
            req = now_kst()
            t0 = time.time()
            code, data = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1m', 'count': 200, 'before': before, 'adjusted': True}, timeout=12)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if code != 200:
                failures.append(f'{sym}:HTTP_{code}')
                break
            result = _result_dict(data)
            candles = result.get('candles', []) if isinstance(result, dict) else []
            page_times = []
            for c in candles if isinstance(candles, list) else []:
                ts = str(c.get('timestamp', ''))
                if _completed_session_candle(ts, None, cal.get('regular_start'), cal.get('regular_end')):
                    dt = _parse_iso(ts)
                    page_times.append(dt)
                    collected[ts] = _us_candle_row_from_api(sym, c, req, rec, latency)
            oldest = min((x for x in page_times if x), default=None)
            if oldest and oldest <= start:
                break
            nxt = result.get('nextBefore') if isinstance(result, dict) else None
            if not nxt:
                break
            before = str(nxt)
            _market_data_request_gap()
        by_minute = {}
        for ts, row in collected.items():
            dt = _parse_iso(ts)
            if dt:
                by_minute[dt.replace(second=0, microsecond=0)] = row
        missing = [t for t in _us_expected_candle_times(start, end) if t not in by_minute]
        for target in missing:
            row, is_source_gap, evidence = _verify_us_source_gap(sym, target, cal)
            if row:
                dt = _parse_iso(row.get('timestamp'))
                by_minute[dt.replace(second=0, microsecond=0)] = row
            elif is_source_gap:
                verified_gaps.setdefault(sym, []).append({'timestamp': target.isoformat(), 'evidence': evidence})
            else:
                failures.append(f'{sym}:TARGETED_BACKFILL_FAILED:{target.isoformat()}')
        rows = [by_minute[k] for k in sorted(by_minute) if start <= k < end]
        _rewrite_csv(us_data_path('candles_1m', sym), headers, rows)
        allowed = {_parse_iso(x['timestamp']).replace(second=0, microsecond=0) for x in verified_gaps.get(sym, []) if _parse_iso(x.get('timestamp'))}
        residual = [t for t in _us_expected_candle_times(start, end) if t not in by_minute and t not in allowed]
        boundary_ok = (start in by_minute or start in allowed) and (end - timedelta(minutes=1) in by_minute or end - timedelta(minutes=1) in allowed)
        if residual or not rows or (not boundary_ok):
            failures.append(f'{sym}:CANDLES_{len(rows)}:RESIDUAL_{len(residual)}:BOUNDARY_{boundary_ok}')
    state['verified_source_gaps'] = verified_gaps
    gap_path = os.path.join(us_market_data_dir(), f'verified_source_gaps_{us_trade_date_from_calendar()}.json')
    with open(gap_path, 'w', encoding='utf-8') as f:
        json.dump({'trade_date': us_trade_date_from_calendar(), 'verified_source_gaps': verified_gaps}, f, ensure_ascii=False, indent=2)
    return (not failures, failures)

def repair_us_required_files_before_backup():
    """백업 직전 재조회 가능한 필수 자료를 복구한다. 기존 파일은 성공 응답으로만 교체한다."""
    failures = []
    price_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'last_price', 'currency']
    req = now_kst()
    t0 = time.time()
    code, data = api_get('/api/v1/prices', params={'symbols': ','.join(US_SYMBOLS)}, timeout=12)
    rec = now_kst()
    latency = round((time.time() - t0) * 1000, 3)
    seen_prices = set()
    if code == 200:
        for item in data.get('result', []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            sym = str(item.get('symbol', '')).upper()
            if sym not in US_SYMBOLS:
                continue
            seen_prices.add(sym)
            write_row(us_data_path('prices', sym), price_headers, {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': item.get('timestamp', ''), 'last_price': item.get('lastPrice', 0), 'currency': item.get('currency', 'USD')})
    for sym in US_SYMBOLS:
        if not _read_csv_rows(us_data_path('prices', sym)) and sym not in seen_prices:
            failures.append(f'{sym}:PRICES_HTTP_{code}')
    daily_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'currency']
    meta_headers = ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'stock_http', 'warning_http', 'limits_http', 'stock_json', 'warning_json', 'limits_json']
    for sym in US_SYMBOLS:
        if not _read_csv_rows(us_data_path('candles_1d', sym)):
            req = now_kst()
            t0 = time.time()
            c, d = api_get('/api/v1/candles', params={'symbol': sym, 'interval': '1d', 'count': 200, 'adjusted': True}, timeout=12)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if c == 200:
                rows = []
                for x in reversed(_result_dict(d).get('candles', []) if isinstance(_result_dict(d).get('candles', []), list) else []):
                    if isinstance(x, dict):
                        rows.append({'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': x.get('timestamp', ''), 'open': x.get('openPrice', 0), 'high': x.get('highPrice', 0), 'low': x.get('lowPrice', 0), 'close': x.get('closePrice', 0), 'volume': x.get('volume', 0), 'currency': x.get('currency', 'USD')})
                if rows:
                    _rewrite_csv(us_data_path('candles_1d', sym), daily_headers, rows)
            if not _read_csv_rows(us_data_path('candles_1d', sym)):
                failures.append(f'{sym}:DAILY_HTTP_{c}')
        metadata = _read_csv_rows(us_data_path('metadata', sym))
        meta_ok = bool(metadata) and all((str(metadata[-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http')))
        if not meta_ok:
            req = now_kst()
            t0 = time.time()
            c1, d1 = api_get('/api/v1/stocks', params={'symbols': sym}, timeout=8)
            _market_data_request_gap()
            c2, d2 = api_get(f'/api/v1/stocks/{sym}/warnings', timeout=8)
            _market_data_request_gap()
            c3, d3 = api_get('/api/v1/price-limits', params={'symbol': sym}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            if c1 == c2 == c3 == 200:
                _rewrite_csv(us_data_path('metadata', sym), meta_headers, [{'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'stock_http': c1, 'warning_http': c2, 'limits_http': c3, 'stock_json': json.dumps(d1, ensure_ascii=False, separators=(',', ':'))[:10000], 'warning_json': json.dumps(d2, ensure_ascii=False, separators=(',', ':'))[:10000], 'limits_json': json.dumps(d3, ensure_ascii=False, separators=(',', ':'))[:10000]}])
            else:
                failures.append(f'{sym}:METADATA_HTTP_{c1}_{c2}_{c3}')
        if not _read_csv_rows(us_data_path('orderbook', sym)):
            req = now_kst()
            t0 = time.time()
            c, d = api_get('/api/v1/orderbook', params={'symbol': sym}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            r = _result_dict(d)
            asks = r.get('asks', []) if isinstance(r.get('asks', []), list) else []
            bids = r.get('bids', []) if isinstance(r.get('bids', []), list) else []
            ts = str(r.get('timestamp', ''))
            if c == 200 and ts:
                write_row_unique(us_data_path('orderbook', sym), ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'api_timestamp', 'best_ask', 'best_bid', 'spread', 'ask_total_volume', 'bid_total_volume', 'asks_json', 'bids_json'], {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'api_timestamp': ts, 'best_ask': asks[0].get('price', 0) if asks else 0, 'best_bid': bids[0].get('price', 0) if bids else 0, 'spread': to_float(asks[0].get('price', 0)) - to_float(bids[0].get('price', 0)) if asks and bids else 0, 'ask_total_volume': sum((to_float(x.get('volume', 0)) for x in asks if isinstance(x, dict))), 'bid_total_volume': sum((to_float(x.get('volume', 0)) for x in bids if isinstance(x, dict))), 'asks_json': json.dumps(asks, separators=(',', ':')), 'bids_json': json.dumps(bids, separators=(',', ':'))}, ['symbol', 'api_timestamp'])
            if not _read_csv_rows(us_data_path('orderbook', sym)):
                failures.append(f'{sym}:ORDERBOOK_HTTP_{c}')
        if not _read_csv_rows(us_data_path('trades', sym)):
            req = now_kst()
            t0 = time.time()
            c, d = api_get('/api/v1/trades', params={'symbol': sym, 'count': 50}, timeout=8)
            rec = now_kst()
            latency = round((time.time() - t0) * 1000, 3)
            for x in reversed(d.get('result', []) if c == 200 and isinstance(d, dict) and isinstance(d.get('result', []), list) else []):
                if not isinstance(x, dict) or not x.get('timestamp'):
                    continue
                write_row_unique(us_data_path('trades', sym), ['requested_at', 'received_at', 'saved_at', 'latency_ms', 'symbol', 'timestamp', 'price', 'volume', 'trade_value', 'currency'], {'requested_at': req.isoformat(), 'received_at': rec.isoformat(), 'saved_at': now_text(), 'latency_ms': latency, 'symbol': sym, 'timestamp': x.get('timestamp', ''), 'price': x.get('price', 0), 'volume': x.get('volume', 0), 'trade_value': round(to_float(x.get('price', 0)) * to_float(x.get('volume', 0)), 4), 'currency': x.get('currency', 'USD')}, ['symbol', 'timestamp', 'price', 'volume'])
            if not _read_csv_rows(us_data_path('trades', sym)):
                failures.append(f'{sym}:TRADES_HTTP_{c}')
    return failures

def audit_us_grade1():
    cal = S.setdefault('us_market_data_capture', {}).get('calendar', {})
    start = _parse_iso(cal.get('regular_start'))
    end = _parse_iso(cal.get('regular_end'))
    failures = []
    details = {}
    if not start or not end:
        return {'grade': 'FAILED', 'failures': ['US_CALENDAR_INVALID'], 'details': {}}
    verified = S.setdefault('us_market_data_capture', {}).get('verified_source_gaps', {}) or {}
    total_verified = 0
    for sym in US_SYMBOLS:
        rows = _read_csv_rows(us_data_path('candles_1m', sym))
        times = [_parse_iso(x.get('timestamp')) for x in rows]
        times = [x.replace(second=0, microsecond=0) for x in times if x]
        duplicate = len(times) - len(set(times))
        reverse = sum((1 for a, b in zip(times, times[1:]) if b <= a))
        future = sum((1 for x in times if x >= end))
        bad = sum((1 for x in rows if any((str(x.get(k, '')) == '' for k in ('open', 'high', 'low', 'close', 'volume', 'estimated_trade_value')))))
        expected_times = _us_expected_candle_times(start, end)
        have = set(times)
        missing_times = [t for t in expected_times if t not in have]
        allowed = {_parse_iso(x.get('timestamp')).replace(second=0, microsecond=0) for x in verified.get(sym, []) if _parse_iso(x.get('timestamp'))}
        source_gap_ok = set(missing_times) == allowed
        total_verified += len(allowed)
        required = {'prices': _read_csv_rows(us_data_path('prices', sym)), 'daily': _read_csv_rows(us_data_path('candles_1d', sym)), 'orderbook': _read_csv_rows(us_data_path('orderbook', sym)), 'trades': _read_csv_rows(us_data_path('trades', sym)), 'metadata': _read_csv_rows(us_data_path('metadata', sym))}
        missing = [k for k, v in required.items() if not v]
        meta_ok = bool(required['metadata']) and all((str(required['metadata'][-1].get(k, '')) == '200' for k in ('stock_http', 'warning_http', 'limits_http')))
        if not meta_ok and 'metadata_http' not in missing:
            missing.append('metadata_http')
        boundary_ok = (start in have or start in allowed) and (end - timedelta(minutes=1) in have or end - timedelta(minutes=1) in allowed)
        ok = boundary_ok and duplicate == 0 and (reverse == 0) and (future == 0) and (bad == 0) and (not missing) and source_gap_ok
        if not ok:
            failures.append(f"{sym}:rows={len(rows)},missing_minutes={len(missing_times)},verified_source_gaps={len(allowed)},missing_ohlcv={bad},missing_types={','.join(missing)}")
        details[sym] = {'rows': len(rows), 'first': times[0].isoformat() if times else '', 'last': times[-1].isoformat() if times else '', 'missing_minutes': [x.isoformat() for x in missing_times], 'verified_source_gaps': [x.isoformat() for x in sorted(allowed)], 'duplicate': duplicate, 'reverse': reverse, 'future': future, 'ok': ok}
    raw_path = os.path.join(raw_market_dir('US'), f'api_{us_trade_date_from_calendar()}.jsonl')
    if not os.path.isfile(raw_path) or os.path.getsize(raw_path) == 0:
        failures.append('RAW_API_RESPONSES_MISSING')
    grade = 'GRADE_2_PARTIAL' if failures else 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS' if total_verified else 'GRADE_1'
    return {'grade': grade, 'failures': failures, 'details': details, 'verified_source_gap_count': total_verified, 'verified_source_gaps': verified}

def _us_backup_source_files(base):
    """미국 거래일 원본만 백업. ZIP/drive_verify/임시파일은 절대 포함하지 않는다."""
    out = []
    base_abs = os.path.abspath(base)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != 'drive_verify']
        for fn in files:
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, base).replace(os.sep, '/')
            if rel.startswith('drive_verify/') or fn.lower().endswith('.zip') or fn.endswith('.tmp'):
                continue
            if not os.path.isfile(fp):
                continue
            if not os.path.abspath(fp).startswith(base_abs + os.sep):
                continue
            out.append((rel, fp))
    out.sort(key=lambda x: x[0])
    return out

def _create_us_backup_zip_unlocked():
    """미국 품질검사 → 원본만 임시 ZIP → CRC/내부검증 → 성공본 원자적 교체."""
    repair_failures = repair_us_required_files_before_backup()
    ok = False
    backfill_failures = []
    quality = {'grade': 'FAILED', 'failures': ['NOT_CHECKED'], 'details': {}}
    for grade1_pass in range(1, 4):
        pass_ok, pass_failures = finalize_us_candles_grade1()
        quality = audit_us_grade1()
        ok = pass_ok and quality.get('grade') in {'GRADE_1', 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS'}
        backfill_failures.extend([f'PASS_{grade1_pass}:{x}' for x in pass_failures])
        if ok:
            break
        time.sleep(min(grade1_pass * 2, 5))
    quality['repair_failures'] = repair_failures
    quality['backfill_ok'] = ok
    quality['backfill_failures'] = backfill_failures
    _atomic_json_write(os.path.join(us_market_data_dir(), f'grade1_report_{us_trade_date_from_calendar()}.json'), quality)
    if not ok:
        raise RuntimeError('미국 백업 품질검사 미통과: ' + ' | '.join(map(str, quality.get('failures', [])[:12]))[:1400])
    trade_date = us_trade_date_from_calendar()
    base = us_day_dir()
    source_files = _us_backup_source_files(base)
    path = us_backup_zip_path(trade_date)
    tmp_path = os.path.join(BACKUP_ROOT, 'US', f'.backup_US_{trade_date}_{uuid.uuid4().hex}.tmp.zip')
    count = len(source_files)
    size = sum(os.path.getsize(fp) for _, fp in source_files)
    manifest = {
        'created_at_kst': now_text(), 'version': OPERATING_VERSION,
        'toss_openapi_spec_version': TOSS_OPENAPI_SPEC_VERSION, 'market': 'US',
        'session': 'REGULAR_ONLY', 'trade_date': trade_date,
        'regular_start': str(S.setdefault('us_market_data_capture', {}).get('calendar', {}).get('regular_start', '')),
        'regular_end': str(S.setdefault('us_market_data_capture', {}).get('calendar', {}).get('regular_end', '')),
        'symbols': US_SYMBOLS, 'included_files': count, 'uncompressed_bytes': size,
        'data_quality_grade': quality.get('grade'), 'data_quality_failures': quality.get('failures', []),
        'verified_source_gap_count': quality.get('verified_source_gap_count', 0),
        'verified_source_gaps': quality.get('verified_source_gaps', {}),
        'paper_only_mode': True, 'real_order_enabled': False, 'real_auto_buy': False, 'real_auto_sell': False,
        'nested_zip_excluded': True, 'drive_verify_excluded': True,
    }
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for rel, fp in source_files:
                z.write(fp, rel)
            z.writestr('backup_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        report = inspect_downloaded_us_backup_zip(tmp_path, trade_date)
        if report.get('grade') not in {'GRADE_1', 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS'}:
            raise RuntimeError('미국 로컬 백업 재검증 실패: ' + ' | '.join(map(str, report.get('failures', [])[:12]))[:1400])
        os.replace(tmp_path, path)
        with LOCK:
            S.setdefault('us_market_data_capture', {})['local_backup_verify'] = {
                'checked_at': now_text(), 'grade': report.get('grade', 'FAILED'),
                'file': os.path.basename(path), 'size': os.path.getsize(path),
                'included_files': count, 'uncompressed_bytes': size,
            }
        return path, quality
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def us_backup_zip_path(trade_date=None):
    trade_date = trade_date or us_trade_date_from_calendar()
    os.makedirs(os.path.join(BACKUP_ROOT, 'US'), exist_ok=True)
    return os.path.join(BACKUP_ROOT, 'US', f'backup_US_{trade_date}.zip')

def create_us_backup_zip():
    """수동 다운로드와 자동 백업이 겹쳐도 ZIP 생성은 한 번만 수행한다."""
    with BACKUP_LOCK:
        return _create_us_backup_zip_unlocked()


def _us_backup_failure_should_notify(trade_date, signature):
    """미국 백업 실패도 거래일당 최초 1회만 알린다."""
    completed_map = S.setdefault('us_backup_completed', {})
    with LOCK:
        item = completed_map.get(trade_date, {})
        if not isinstance(item, dict):
            item = {}
        already = bool(item.get('failure_notified_once'))
        item['last_failure_signature'] = str(signature)[:1200]
        item['last_failure_seen_at'] = now_text()
        if not already:
            item['failure_notified_once'] = True
            item['last_failure_notified_at'] = time.time()
        completed_map[trade_date] = item
    save_state()
    return not already

def maybe_send_us_backup():
    if not ENABLE_US_MARKET_DATA_CAPTURE:
        return
    state = S.setdefault('us_market_data_capture', {})
    cal = state.get('calendar', {})
    trade_date = str(cal.get('date', ''))
    end = _parse_iso(cal.get('regular_end'))
    if not trade_date or not end:
        return
    nowv = now_kst()
    if not end + timedelta(minutes=US_BACKUP_DELAY_MIN) <= nowv <= end + timedelta(hours=12):
        return
    completed_map = S.setdefault('us_backup_completed', {})
    done = completed_map.get(trade_date, {})
    if isinstance(done, dict) and (done.get('drive_reverified') or done.get('restored_from_drive') or done.get('completed')):
        return
    attempt_key = f'US_BACKUP_ATTEMPT_{trade_date}'
    with LOCK:
        last_attempt = to_float(S['last_alert'].get(attempt_key, 0))
        if time.time() - last_attempt < 600:
            return
        S['last_alert'][attempt_key] = time.time()
    if GOOGLE_DRIVE_UPLOAD_ENABLED and google_drive_credentials_ready(True):
        try:
            existing, existing_report, checked = find_verified_existing_us_backup_on_drive(trade_date)
            if existing:
                with LOCK:
                    completed_map[trade_date] = {'completed_at': now_text(), 'grade': existing_report.get('grade', 'GRADE_1'), 'file_name': str(existing.get('name', '')), 'file_id': str(existing.get('id', '')), 'restored_from_drive': True}
                save_state()
                send_telegram(f"🇺🇸 미국 정규장 백업 {existing_report.get('grade', 'GRADE_1')}\n거래일: {trade_date}\n✅ Drive 기존 정상백업 재다운로드·내부검증 완료\n중복 업로드 없음\n실주문: 차단", force=True)
                return
        except Exception as e:
            set_error(f'미국 Drive 기존백업 사전검증 오류: {e}')
    path, quality = create_us_backup_zip()
    grade = quality.get('grade', 'FAILED')
    acceptable = bool(quality.get('backfill_ok')) and grade in {'GRADE_1', 'GRADE_1_WITH_VERIFIED_SOURCE_GAPS'}
    msg = f'🇺🇸 미국 정규장 백업 {grade}\n거래일: {trade_date}\n종목: {len(US_SYMBOLS)}개\n실주문: 차단'
    if not acceptable:
        failures = quality.get('failures', []) or quality.get('backfill_failures', [])
        msg += '\n❌ 품질검사 미통과 - Drive 업로드 보류'
        if failures:
            msg += '\n실패: ' + ' | '.join(map(str, failures[:8]))[:800]
        msg += '\n자동 재시도는 조용히 계속합니다.'
        signature = 'US_QUALITY:' + '|'.join(map(str, failures[:8]))[:900]
        if _us_backup_failure_should_notify(trade_date, signature):
            send_telegram(msg, force=True)
        return
    completed = not GOOGLE_DRIVE_UPLOAD_ENABLED
    result = {}
    if GOOGLE_DRIVE_UPLOAD_ENABLED and google_drive_credentials_ready(True):
        drive_ok, result = upload_backup_to_google_drive(path)
        if drive_ok:
            try:
                verify_ok, verify_report = verify_us_backup_file_from_google_drive(result, trade_date)
            except Exception as e:
                verify_ok, verify_report = (False, {'grade': 'FAILED', 'failures': [str(e)]})
            completed = verify_ok
            if verify_ok:
                msg += '\n✅ Drive 업로드 성공\n✅ Drive 재다운로드·CRC·14종목 1분봉·호가·체결·메타데이터 재검증 성공'
            else:
                msg += '\n❌ Drive 업로드 후 재검증 실패\n성공 처리하지 않음 / 10분 뒤 기존 Drive 파일부터 재검증\n실패: ' + ' | '.join(map(str, verify_report.get('failures', [])[:8]))[:800]
        else:
            completed = False
            msg += '\n❌ Drive 업로드 실패: ' + str(result.get('error', ''))[:300]
    elif GOOGLE_DRIVE_UPLOAD_ENABLED:
        completed = False
        msg += '\n❌ Drive 설정 미완료'
    if completed:
        with LOCK:
            completed_map[trade_date] = {'completed_at': now_text(), 'grade': grade, 'file_name': str(result.get('name', os.path.basename(path))) if isinstance(result, dict) else os.path.basename(path), 'file_id': str(result.get('id', '')) if isinstance(result, dict) else '', 'drive_reverified': bool(GOOGLE_DRIVE_UPLOAD_ENABLED)}
        save_state()
    if completed:
        send_telegram(msg, force=True)
    else:
        signature = 'US_DRIVE:' + msg[-900:]
        if _us_backup_failure_should_notify(trade_date, signature):
            send_telegram(msg, force=True)

def _kr_backup_failure_should_notify(trade_date, signature, cooldown_sec=86400):
    """한국 백업 실패는 거래일당 최초 1회만 알린다. 자동 재시도는 조용히 계속한다."""
    completed_map = S.setdefault('kr_backup_completed', {})
    with LOCK:
        item = completed_map.get(trade_date, {})
        if not isinstance(item, dict):
            item = {}
        item['last_failure_signature'] = str(signature)[:1200]
        item['last_failure_seen_at'] = now_text()
        already = bool(item.get('failure_notified_once'))
        if not already:
            item['failure_notified_once'] = True
            item['last_failure_notified_at'] = time.time()
            item['last_failure_notified_text'] = now_text()
        completed_map[trade_date] = item
    save_state()
    return not already

def _kr_backup_mark_success_clear_failure(trade_date):
    completed_map = S.setdefault('kr_backup_completed', {})
    with LOCK:
        item = completed_map.get(trade_date, {})
        if not isinstance(item, dict):
            item = {}
        for k in ('last_failure_signature', 'last_failure_seen_at', 'last_failure_notified_at', 'last_failure_notified_text', 'failure_notified_once'):
            item.pop(k, None)
        completed_map[trade_date] = item
    save_state()

def maybe_send_daily_backup():
    if not ENABLE_DAILY_BACKUP_ALERT:
        return
    n = now_kst()
    if is_weekend_kst() or (n.hour, n.minute) < (15, 35):
        return
    trade_date = today()
    key = f'BACKUP_SENT_{trade_date}'
    attempt_key = key + '_ATTEMPT'
    completed_map = S.setdefault('kr_backup_completed', {})
    done = completed_map.get(trade_date, {})
    if isinstance(done, dict) and done.get('drive_reverified'):
        return
    with LOCK:
        last_attempt = to_float(S['last_alert'].get(attempt_key, 0))
        if time.time() - last_attempt < 600:
            return
        S['last_alert'][attempt_key] = time.time()
    url = f'{APP_URL}/download_backup' if APP_URL else '/download_backup'
    oauth_url = f'{APP_URL}/google/oauth/start' if APP_URL else '/google/oauth/start'
    # 핵심 원칙: GRADE 검증보다 먼저 당일 실제 원본을 복구 ZIP으로 보존한다.
    # 검증기가 오판정해도 사용자가 다시 데이터를 찾지 않도록 한다.
    rescue_path = None
    rescue_err = ''
    try:
        rescue_path = preserve_kr_raw_before_grade_check()
    except Exception as e:
        rescue_err = str(e)[:500]
    try:
        path = create_backup_zip()
    except Exception as e:
        err_text = str(e)[:1200]
        signature = 'LOCAL_BACKUP_VERIFY:' + err_text[:900]
        drive_rescue_note = ''
        if rescue_path and GOOGLE_DRIVE_UPLOAD_ENABLED and google_drive_credentials_ready(require_refresh=True):
            try:
                raw_drive_ok, raw_drive_result = upload_backup_to_google_drive(rescue_path)
                if raw_drive_ok:
                    drive_rescue_note = f"\n✅ RAW 복구 ZIP Drive 보존 성공: {raw_drive_result.get('name', os.path.basename(rescue_path))}"
                else:
                    drive_rescue_note = f"\n⚠️ RAW 복구 ZIP Drive 업로드 실패: {str(raw_drive_result.get('error',''))[:250]}"
            except Exception as de:
                drive_rescue_note = f"\n⚠️ RAW 복구 ZIP Drive 업로드 예외: {str(de)[:250]}"
        if _kr_backup_failure_should_notify(trade_date, signature):
            rescue_note = (f"\n✅ 당일 실제 원본 RAW 복구 ZIP 보존: {os.path.basename(rescue_path)}" if rescue_path else f"\n⚠️ RAW 복구 ZIP 생성 실패: {rescue_err}")
            send_telegram(f'🇰🇷 한국시장 백업 생성/검증 실패\n날짜: {trade_date}\n오류: {err_text}\nGRADE 성공본은 교체하지 않음' + rescue_note + drive_rescue_note + '\n자동 재시도는 계속하지만 같은 거래일의 실패 알림은 더 이상 반복하지 않습니다.', force=True)
        return
    final_grade = S.setdefault('market_data_capture', {}).get('final_grade', 'FAILED')
    caption = f'🇰🇷 한국시장 데이터 백업 {final_grade}\n날짜: {trade_date}\n시간: {now_short()}\n한국 동일조건 수집 종목: {len(ALL26_SYMBOLS)}개\n미국 데이터: 미포함\n다운로드 링크: {url}'
    with LOCK:
        current = completed_map.get(trade_date, {})
        if not isinstance(current, dict):
            current = {}
        current.update({'local_verified': True, 'local_verified_at': now_text(), 'local_file': os.path.basename(path), 'local_size': os.path.getsize(path), 'drive_reverified': False})
        completed_map[trade_date] = current
    save_state()
    if GOOGLE_DRIVE_UPLOAD_ENABLED:
        if not google_drive_credentials_ready(require_refresh=True):
            signature = 'DRIVE_CONFIG_INCOMPLETE'
            if _kr_backup_failure_should_notify(trade_date, signature):
                tg_ok, tg_msg = send_telegram_file(path, caption + '\n❌ Google Drive 설정 미완료\n✅ 로컬 GRADE_1 ZIP 보존', force=True)
                buttons = [[telegram_button('Google Drive 재승인', oauth_url)], [telegram_button('백업 다운로드', url)]]
                send_telegram(caption + '\n❌ Google Drive 업로드: 설정 미완료' + ('\n✅ Telegram ZIP 외부사본 전송 성공' if tg_ok else f'\n⚠️ Telegram ZIP 전송 실패: {tg_msg[:300]}') + '\n같은 거래일에는 반복 알림하지 않습니다.', buttons, force=True)
            return
        drive_ok, result = upload_backup_to_google_drive(path)
        if drive_ok:
            size_mb = int(result.get('size', 0)) / (1024 * 1024)
            drive_link = str(result.get('webViewLink', ''))
            try:
                verify_ok, verify_report = verify_kr_backup_file_from_google_drive(result, trade_date)
            except Exception as e:
                verify_ok, verify_report = (False, {'failures': [str(e)]})
            if verify_ok:
                msg = caption + '\n✅ Google Drive 업로드 성공' + '\n✅ Drive 재다운로드·CRC·26종목 390봉·호가·체결·90계좌·메타데이터 GRADE_1' + f'\n파일 크기: {size_mb:.1f} MB' + f"\nDrive 파일 ID: {result.get('id', '')}"
                buttons = [[telegram_button('Google Drive에서 보기', drive_link)]] if drive_link else []
                send_telegram(msg, buttons, force=True)
                with LOCK:
                    S['last_alert'][key] = time.time()
                    completed_map[trade_date] = {'local_verified': True, 'local_verified_at': current.get('local_verified_at', now_text()), 'local_file': os.path.basename(path), 'local_size': os.path.getsize(path), 'drive_reverified': True, 'drive_verified_at': now_text(), 'file_id': str(result.get('id', '')), 'file_name': str(result.get('name', os.path.basename(path)))}
                _kr_backup_mark_success_clear_failure(trade_date)
            else:
                failed = verify_report.get('failures', [])
                signature = 'DRIVE_REVERIFY:' + '|'.join(map(str, failed[:12]))[:900]
                if _kr_backup_failure_should_notify(trade_date, signature):
                    tg_ok, tg_msg = send_telegram_file(path, caption + '\n⚠️ Drive 업로드 후 재검증 실패 / 로컬 GRADE_1 사본', force=True)
                    send_telegram(caption + '\n❌ Drive 업로드 후 재검증 실패' + f"\n검증 대상 파일 ID: {result.get('id', '')}" + f"\n파일: {verify_report.get('drive_file_name', result.get('name', ''))}" + f"\n실패 항목: {' | '.join(failed[:12])[:1200]}" + ('\n✅ Telegram ZIP 외부사본 전송 성공' if tg_ok else f'\n⚠️ Telegram ZIP 전송 실패: {tg_msg[:300]}') + '\n자동 재시도는 계속하지만 같은 거래일의 실패 알림은 더 이상 반복하지 않습니다.', [[telegram_button('Google Drive에서 보기', drive_link)]] if drive_link else [], force=True)
        else:
            err = str(result.get('error', ''))
            auth_required = '재승인 필요' in err or 'invalid_grant' in err.lower() or 'expired' in err.lower() or ('revoked' in err.lower())
            signature = ('DRIVE_AUTH:' if auth_required else 'DRIVE_UPLOAD:') + err[:900]
            should_notify = _kr_backup_failure_should_notify(trade_date, signature)
            tg_ok, tg_msg = (False, '반복 알림 억제')
            if should_notify:
                tg_ok, tg_msg = send_telegram_file(path, caption + '\n❌ Google Drive 업로드 실패 / ✅ 로컬 GRADE_1 복구 사본', force=True)
            buttons = []
            if auth_required:
                buttons.append([telegram_button('Google Drive 재승인', oauth_url)])
            buttons.append([telegram_button('백업 다운로드', url)])
            if should_notify:
                send_telegram(caption + '\n❌ Google Drive 업로드 실패' + f'\n오류: {err[:700]}' + ('\n✅ Telegram ZIP 외부사본 전송 성공' if tg_ok else f'\n⚠️ Telegram ZIP 전송 실패: {tg_msg[:300]}') + ('\nGoogle Drive 재승인 전까지 같은 인증 실패 알림은 반복하지 않습니다.' if auth_required else '\n같은 업로드 실패 알림은 6시간 동안 반복하지 않습니다.') + '\n서버의 검증된 ZIP은 유지됩니다.', buttons, force=True)
    else:
        ok, msg = send_telegram_file(path, caption, force=True)
        if not ok:
            send_telegram(caption + f'\n파일전송 실패: {msg}', [[telegram_button('백업 다운로드', url)]], force=True)
        else:
            with LOCK:
                S['last_alert'][key] = time.time()
                completed_map[trade_date] = {'local_verified': True, 'local_verified_at': now_text(), 'local_file': os.path.basename(path), 'local_size': os.path.getsize(path), 'drive_reverified': False, 'telegram_exported': True}
            save_state()

def loop():
    """DATA+PAPER ONLY 핵심 루프: KR/US 데이터 수집 + 가상매매 + 원본보존/백업만 수행한다. 실주문/추천 실행 없음."""
    load_state()
    ensure_multi_ai_states()
    save_state()
    counter = 0
    initialized = False
    while True:
        try:
            us_open_weekend = False
            if ENABLE_US_MARKET_DATA_CAPTURE:
                try:
                    refresh_us_market_calendar(False)
                    us_open_weekend, _ = us_regular_market_open_now()
                except Exception as e:
                    set_error(f'미국 캘린더 오류: {e}')
            if is_weekend_kst():
                # 한국 주말에는 한국 API/가상매매를 절대 돌리지 않는다.
                # 미국 금요일 장이 한국 토요일에 열려 있으면 미국 수집/백업만 수행한다.
                if ENABLE_US_MARKET_DATA_CAPTURE:
                    try:
                        capture_us_market_data()
                    except Exception as e:
                        set_error(f'주말 미국 데이터 수집 오류: {e}')
                    try:
                        maybe_send_us_backup()
                    except Exception as e:
                        set_error(f'주말 미국 백업 오류: {e}')
                set_status_once('WEEKEND_PAUSE', '한국 주말 휴무 / 미국 데이터·백업만 운영' if us_open_weekend else '한국 주말 휴무 / 미국 백업만 확인', 1800)
                time.sleep(max(10, REFRESH_SEC))
                continue
            if not initialized:
                get_token()
                refresh_kr_market_calendar(force=True)
                if ENABLE_US_MARKET_DATA_CAPTURE:
                    refresh_us_market_calendar(force=True)
                load_prices()
                calc_wma_all()
                calc_scores()
                initialized = True
            refresh_kr_market_calendar(force=False)
            load_prices()
            try:
                maybe_capture_toss_market_data()
            except Exception as e:
                set_error(f'한국 데이터 수집 오류: {e}')
            try:
                capture_us_market_data()
            except Exception as e:
                set_error(f'미국 데이터 수집 오류: {e}')
            calc_wma_all()
            calc_scores()
            write_logs()
            update_paper_asset()
            try:
                gate_ok, _ = market_safety_gate()
                if gate_ok:
                    run_paper_ai_if_enabled()
                    run_multi_paper_ais()
            except Exception as e:
                set_error(f'가상매매 오류: {e}')
            try:
                maybe_send_daily_backup()
            except Exception as e:
                set_error(f'한국 백업 오류: {e}')
            try:
                maybe_send_us_backup()
            except Exception as e:
                set_error(f'미국 백업 오류: {e}')
            ensure_token()
            counter += 1
            if counter % max(1, int(60 / max(10, REFRESH_SEC))) == 0:
                write_collector_heartbeat()
        except Exception as e:
            set_error(f'루프 오류: {e}')
        time.sleep(max(10, REFRESH_SEC))
CSS = '\n<style>\n*{box-sizing:border-box}body{margin:0;padding:12px;background:#07090f;color:#eef1f7;font-family:Arial,sans-serif;font-size:13px}h1{margin:4px 0;text-align:center;font-size:22px}.sub{text-align:center;color:#8d95a7;font-size:11px;margin-bottom:12px}.grid{display:grid;grid-template-columns:minmax(260px,.9fr) minmax(440px,1.55fr) minmax(300px,1fr);gap:12px;align-items:start}.card{background:#111522;border:1px solid #242a3a;border-radius:12px;padding:12px;margin-bottom:12px;box-shadow:0 4px 18px rgba(0,0,0,.18)}.card h2{margin:0 0 9px;font-size:15px;color:#c2c8d5}.big{font-size:24px;font-weight:700}.mid{font-size:18px;font-weight:700}.small{font-size:11px;color:#929bad}.red{color:#ff6262}.blue{color:#63a0ff}.green{color:#55df91}.yellow{color:#ffd75a}.gray{color:#8b93a5}table{width:100%;border-collapse:collapse;font-size:11px}th{text-align:left;color:#9aa3b6;background:#171c2a;padding:7px;position:sticky;top:0}td{padding:7px;border-bottom:1px solid #202637;vertical-align:top}button{border:0;border-radius:7px;padding:8px 11px;margin:3px;font-weight:700;cursor:pointer}.buy{background:#db3038;color:#fff}.sell{background:#2b6cff;color:#fff}.graybtn{background:#343b4d;color:#fff}.gold{background:#ffd75a;color:#111}.paperbtn{background:#7c51e8;color:#fff}input{background:#090c14;color:#fff;border:1px solid #394156;border-radius:6px;padding:7px;width:72px}.progress{width:100%;height:8px;background:#222a3a;border-radius:10px;overflow:hidden;margin:6px 0}.bar{height:100%;background:#ffd75a}.scroll{max-height:680px;overflow:auto}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}.metric{background:#171c2a;border-radius:8px;padding:9px}.metric b{display:block;font-size:16px;margin-top:3px}.tabs{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px}.tabbtn{background:#2a3040;color:#dce1eb;padding:6px 9px}.tabbtn.active{background:#ffd75a;color:#111}.hide{display:none}.badge{display:inline-block;padding:2px 6px;border-radius:10px;background:#252c3d;font-size:10px}.pos{background:#173c2a;color:#65e59a}.neg{background:#4a2025;color:#ff8087}.warn{background:#463b18;color:#ffdd6c}details summary{cursor:pointer;color:#cbd2df;font-weight:700;margin:4px 0}@media(max-width:1150px){.grid{grid-template-columns:1fr 1.5fr}.grid>div:last-child{grid-column:1/-1}}@media(max-width:760px){body{padding:7px}.grid{grid-template-columns:1fr}.summary-grid{grid-template-columns:repeat(2,1fr)}.card{padding:9px}.scroll{max-height:520px}}\n</style>\n'

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == '/google/oauth/start':
            try:
                return self.redirect(google_drive_oauth_start_url())
            except Exception as e:
                return self.result_page('Google Drive OAuth 시작 실패', str(e))
        if path == '/google/oauth/callback':
            try:
                refresh_token = google_drive_exchange_oauth_code(qs)
                token_html = html.escape(refresh_token, quote=True)
                return self.html_response(f"<html><head><meta charset='utf-8'></head><body><h2>Google Drive 승인 성공</h2><p>아래 값을 Render GOOGLE_DRIVE_REFRESH_TOKEN 환경변수에 저장하세요.</p><textarea style='width:100%;height:100px' readonly>{token_html}</textarea></body></html>")
            except Exception as e:
                return self.result_page('Google Drive OAuth 승인 실패', str(e))
        if path in ('/selfcheck', '/configcheck'):
            return self.json_response({'ok': True, 'version': OPERATING_VERSION, 'market_mode': MARKET_MODE, 'paper_only_mode': PAPER_ONLY_MODE, 'real_order_enabled': ENABLE_REAL_ORDER, 'us_real_order_enabled': US_REAL_ORDER_ENABLED, 'real_auto_buy': ENABLE_REAL_AUTO_BUY, 'real_auto_sell': ENABLE_REAL_AUTO_SELL, 'kr_collector_enabled': ENABLE_TOSS_MARKET_DATA_CAPTURE, 'kr_symbol_count': len(ALL26_SYMBOLS), 'us_collector_enabled': ENABLE_US_MARKET_DATA_CAPTURE, 'us_symbol_count': len(US_SYMBOLS), 'paper_auto': ENABLE_PAPER_AUTO, 'paper_accounts': len(MULTI_AI_IDS), 'paper_start_cash_each': MULTI_AI_START_CASH, 'google_drive_upload_enabled': GOOGLE_DRIVE_UPLOAD_ENABLED, 'google_drive_ready': google_drive_credentials_ready(require_refresh=True), 'google_drive_state': dict(S.get('google_drive', {})), 'storage': storage_selfcheck(), 'kr_capture': S.get('market_data_capture', {}), 'us_capture': S.get('us_market_data_capture', {}), 'last_error': S.get('last_error', '')})
        if path == '/rescue_today':
            # GRADE 판정과 무관하게 현재 서버에 존재하는 오늘 KR 원본을 즉시 보존/다운로드한다.
            # 데이터 재작성, 가짜 행 추가, 가격 수정은 하지 않는다.
            try:
                p = create_kr_raw_rescue_backup(today())
                return self.download_file(p, os.path.basename(p), 'application/zip')
            except Exception as e:
                return self.json_response({'ok': False, 'error': str(e), 'date': today()}, status=500)
        if path == '/download_backup':
            p = backup_zip_path()
            if not os.path.isfile(p):
                p = create_backup_zip()
            return self.download_file(p, os.path.basename(p), 'application/zip')
        if path == '/download_us_backup':
            refresh_us_market_calendar(force=True)
            trade_date = us_trade_date_from_calendar()
            p = us_backup_zip_path(trade_date)
            if not os.path.isfile(p):
                p, _ = create_us_backup_zip()
            return self.download_file(p, os.path.basename(p), 'application/zip')
        if path in ('/', '/health'):
            return self.html_response(f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body><h2>{html.escape(OPERATING_VERSION)}</h2><p>운영: KR/US 데이터 수집 + 가상매매 + Drive 백업 전용</p><p>KR {len(ALL26_SYMBOLS)}종목 / US {len(US_SYMBOLS)}종목 / PAPER {len(MULTI_AI_IDS)}계좌</p><p>실주문: {('ON' if ENABLE_REAL_ORDER else 'OFF')} / 자동매수: {('ON' if ENABLE_REAL_AUTO_BUY else 'OFF')} / 자동매도: {('ON' if ENABLE_REAL_AUTO_SELL else 'OFF')}</p><p><a href='/selfcheck'>selfcheck</a> | <a href='/rescue_today'>오늘 KR 원본 구조백업</a> | <a href='/download_backup'>한국 ZIP</a> | <a href='/download_us_backup'>미국 ZIP</a> | <a href='/google/oauth/start'>Drive 재승인</a></p></body></html>")
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        return self.json_response({'ok': False, 'error': 'POST_DISABLED_PAPER_ONLY'}, status=405)

    def download_file(self, path, filename, content_type='application/octet-stream'):
        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(os.path.getsize(path)))
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        with open(path, 'rb') as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                self.wfile.write(b)

    def html_response(self, body, status=200):
        data = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def result_page(self, title, msg):
        return self.html_response(f"<html><meta charset='utf-8'><body><h2>{html.escape(title)}</h2><pre>{html.escape(str(msg))}</pre></body></html>")

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass

def _path_is_under(path, root):
    try:
        p = os.path.abspath(path)
        r = os.path.abspath(root)
        return p == r or p.startswith(r + os.sep)
    except Exception:
        return False


def storage_selfcheck():
    """수집 시작 전에 실제 저장 경로가 쓰기 가능한지 확인한다. /tmp 사용 여부도 명시한다."""
    result = {
        'log_root': LOG_ROOT,
        'backup_root': BACKUP_ROOT,
        'state_path': STATE_PATH,
        'state_backup_path': STATE_BAK_PATH,
        'persistent_disk_mount_path': PERSISTENT_DISK_MOUNT_PATH,
        'ephemeral_storage': not _path_is_under(LOG_ROOT, PERSISTENT_DISK_MOUNT_PATH),
        'require_persistent_storage': REQUIRE_PERSISTENT_STORAGE,
        'allow_ephemeral_storage': ALLOW_EPHEMERAL_STORAGE,
        'strict_persistent_storage': STRICT_PERSISTENT_STORAGE,
        'writable': False,
        'error': '',
    }
    try:
        os.makedirs(LOG_ROOT, exist_ok=True)
        os.makedirs(BACKUP_ROOT, exist_ok=True)
        os.makedirs(os.path.dirname(STATE_PATH) or '.', exist_ok=True)
        os.makedirs(HEALTH_ROOT, exist_ok=True)
        probe = os.path.join(HEALTH_ROOT, '.write_probe')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write(now_text())
            f.flush()
            os.fsync(f.fileno())
        os.remove(probe)
        result['writable'] = True
    except Exception as e:
        result['error'] = str(e)
    return result

def write_collector_heartbeat():
    """수집/백업과 독립된 최소 상태 체크포인트. 실패해도 수집 루프를 중단하지 않는다."""
    try:
        _atomic_json_write(os.path.join(HEALTH_ROOT, 'collector_heartbeat.json'), {
            'time_kst': now_text(), 'version': OPERATING_VERSION,
            'kr_date': today(), 'us_trade_date': us_trade_date_from_calendar(),
            'kr_status': S.get('market_data_capture', {}).get('status', ''),
            'us_status': S.get('us_market_data_capture', {}).get('status', ''),
            'last_error': S.get('last_error', ''),
        })
    except Exception:
        pass

def acquire_single_instance_lock():
    """같은 영구 데이터 경로에 두 프로세스가 동시에 쓰는 것을 차단한다."""
    global INSTANCE_LOCK_HANDLE
    os.makedirs(os.path.dirname(INSTANCE_LOCK_PATH), exist_ok=True)
    handle = open(INSTANCE_LOCK_PATH, 'a+', encoding='utf-8')
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise RuntimeError('이미 다른 collector 인스턴스가 같은 DATA_ROOT를 사용 중입니다.')
    handle.seek(0)
    handle.truncate()
    handle.write(f'pid={os.getpid()} started={now_text()} version={OPERATING_VERSION}\n')
    handle.flush()
    os.fsync(handle.fileno())
    INSTANCE_LOCK_HANDLE = handle
    return True


def print_core_selfcheck():
    print('[CORE DATA/PAPER/BACKUP FROZEN]', flush=True)
    print('version=', OPERATING_VERSION, flush=True)
    print('KR symbols=', len(ALL26_SYMBOLS), 'US symbols=', len(US_SYMBOLS), 'paper accounts=', len(MULTI_AI_IDS), flush=True)
    print('paper_only=', PAPER_ONLY_MODE, 'real_order=', ENABLE_REAL_ORDER, 'real_auto_buy=', ENABLE_REAL_AUTO_BUY, 'real_auto_sell=', ENABLE_REAL_AUTO_SELL, 'us_real_order=', US_REAL_ORDER_ENABLED, flush=True)
    storage = storage_selfcheck()
    print('storage=', storage, flush=True)
    if not storage.get('writable'):
        raise RuntimeError('데이터 저장 경로 쓰기 실패: ' + storage.get('error', ''))
    persistent_issue = bool(
        storage.get('ephemeral_storage')
        or not _path_is_under(BACKUP_ROOT, PERSISTENT_DISK_MOUNT_PATH)
        or not _path_is_under(STATE_PATH, PERSISTENT_DISK_MOUNT_PATH)
    )
    if persistent_issue and REQUIRE_PERSISTENT_STORAGE and not ALLOW_EPHEMERAL_STORAGE:
        msg = (
            'WARNING: Persistent Disk 미연결/미사용. 현재 저장경로를 유지하고 서버는 계속 실행합니다. '
            f'LOG_ROOT={LOG_ROOT} BACKUP_ROOT={BACKUP_ROOT} STATE_PATH={STATE_PATH}. '
            'Drive 백업을 계속 사용하고, 가능하면 Render Persistent Disk를 /var/data에 연결하세요.'
        )
        print(msg, flush=True)
        with LOCK:
            S['last_error'] = now_text() + ' ' + msg
        if STRICT_PERSISTENT_STORAGE:
            raise RuntimeError(msg)
    if not PAPER_ONLY_MODE or ENABLE_REAL_ORDER or ENABLE_REAL_AUTO_BUY or ENABLE_REAL_AUTO_SELL or US_REAL_ORDER_ENABLED:
        raise RuntimeError('실주문 안전차단 실패')
    if not DATA_PAPER_BACKUP_ONLY:
        raise RuntimeError('DATA+PAPER+BACKUP 전용 모드 실패')
    if len(ALL26_SYMBOLS) != 26:
        raise RuntimeError(f'KR 종목 수 오류: {len(ALL26_SYMBOLS)}')
    if len(US_SYMBOLS) != 14:
        raise RuntimeError(f'US 종목 수 오류: {len(US_SYMBOLS)}')
    if len(MULTI_AI_IDS) != 90:
        raise RuntimeError(f'가상계좌 수 오류: {len(MULTI_AI_IDS)}')
if __name__ == '__main__':
    print_core_selfcheck()
    acquire_single_instance_lock()
    threading.Thread(target=loop, daemon=True).start()
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
