from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote_plus
from datetime import datetime, timedelta, timezone
import csv, html, json, math, os, threading, time, urllib.request, xml.etree.ElementTree as ET
import requests

try:
    import pytz
    KST = pytz.timezone('Asia/Seoul')
except Exception:
    KST = timezone(timedelta(hours=9))

PORT = int(os.environ.get('PORT', '10000'))
TOSS_CLIENT_ID = os.environ.get('TOSS_CLIENT_ID', '').strip()
TOSS_CLIENT_SECRET = os.environ.get('TOSS_CLIENT_SECRET', '').strip()
TOSS_ACCOUNT = os.environ.get('TOSS_ACCOUNT', '').strip()
KAKAO_TOKEN = os.environ.get('KAKAO_TOKEN', '').strip()
APP_URL = os.environ.get('APP_URL', '').strip()
ALLOW_REAL_ORDERS = os.environ.get('ALLOW_REAL_ORDERS', 'false').lower() == 'true'
ENABLE_EMERGENCY_AUTO_SELL = os.environ.get('ENABLE_EMERGENCY_AUTO_SELL', 'false').lower() == 'true'
REFRESH_SEC = int(os.environ.get('REFRESH_SEC', '60'))
ENABLE_NEWS = os.environ.get('ENABLE_NEWS', 'true').lower() == 'true'
NEWS_REFRESH_SEC = int(os.environ.get('NEWS_REFRESH_SEC', '600'))
EMERGENCY_COOLDOWN_SEC = int(os.environ.get('EMERGENCY_COOLDOWN_SEC', '1800'))
LOG_ROOT = os.environ.get('LOG_ROOT', 'logs')
STATE_PATH = os.environ.get('STATE_PATH', 'state.json')

DEFAULT_SYMBOLS = [
    {'symbol':'0193T0','name':'하이닉스 레버리지','kind':'lever'},
    {'symbol':'0197X0','name':'하이닉스 인버스','kind':'inverse'},
    {'symbol':'000660','name':'SK하이닉스','kind':'stock'},
    {'symbol':'0193W0','name':'삼성전자 레버리지','kind':'lever'},
    {'symbol':'0193L0','name':'삼성전자 인버스','kind':'inverse'},
    {'symbol':'005930','name':'삼성전자','kind':'stock'},
    {'symbol':'122630','name':'KODEX 레버리지','kind':'market_lever'},
    {'symbol':'252670','name':'KODEX 인버스2X','kind':'market_inverse'},
    {'symbol':'069500','name':'KODEX 200','kind':'market'},
    {'symbol':'233740','name':'코스닥150 레버리지','kind':'kosdaq_lever'},
    {'symbol':'251340','name':'코스닥150 인버스','kind':'kosdaq_inverse'},
    {'symbol':'229200','name':'KODEX 코스닥150','kind':'kosdaq'},
    {'symbol':'494310','name':'반도체 레버리지','kind':'theme_lever'},
    {'symbol':'488080','name':'TIGER 반도체TOP10레버리지','kind':'theme_lever'},
    {'symbol':'469150','name':'AI반도체','kind':'theme'},
    {'symbol':'0100K0','name':'방산 레버리지','kind':'theme_lever'},
    {'symbol':'0080Y0','name':'조선 레버리지','kind':'theme_lever'},
    {'symbol':'462330','name':'2차전지 레버리지','kind':'theme_lever'},
    {'symbol':'0177X0','name':'로봇 휴머노이드','kind':'theme'},
    {'symbol':'445290','name':'로봇액티브','kind':'theme'},
    {'symbol':'433500','name':'원자력','kind':'theme'},
    {'symbol':'487240','name':'AI전력인프라','kind':'theme'},
    {'symbol':'418660','name':'나스닥100 레버리지','kind':'global_lever'},
    {'symbol':'465610','name':'미국빅테크TOP7 레버리지','kind':'global_lever'},
    {'symbol':'225040','name':'S&P500 레버리지','kind':'global_lever'},
    {'symbol':'0127R0','name':'AI클라우드','kind':'theme'},
]


def load_symbols():
    raw = os.environ.get('WATCH_SYMBOLS_JSON','').strip()
    if not raw: return DEFAULT_SYMBOLS
    try: return json.loads(raw)
    except Exception: return DEFAULT_SYMBOLS

SYMBOLS = load_symbols()
SMAP = {x['symbol']:x for x in SYMBOLS}
LOCK = threading.Lock()
STATE = {'real_base':None,'paper_start':None,'paper_cash':None,'paper_positions':{},'paper_realized':0.0,'last_emergency_sell':{},'last_kakao':'','last_error':''}
LATEST = {'updated_at':'','account_seq':None,'total_asset':0,'buying_power_krw':0,'holdings':[],'prices':{},'analysis':{},'market_score':50,'market_mode':'UNKNOWN','news_score':0,'news_items':[],'paper_total':0,'paper_return':0,'real_return':0,'emergency':{'level':0,'reason':''}}
TOKEN = {'value':'','expires_at':0}
NEWS = {'ts':0,'score':0,'items':[]}

def nk(): return datetime.now(KST)
def nts(): return nk().strftime('%Y-%m-%d %H:%M:%S')
def day(): return nk().strftime('%Y-%m-%d')
def esc(x): return html.escape(str(x))
def fnum(x,d=0.0):
    try: return float(str(x).replace(',',''))
    except Exception: return d
def inum(x,d=0):
    try: return int(math.floor(float(str(x).replace(',',''))))
    except Exception: return d
def won(x):
    try: return f"{int(round(float(x))):,}원"
    except Exception: return '0원'
def pct(x):
    try: return f"{float(x):+.2f}%"
    except Exception: return '+0.00%'
def mkdir(p): os.makedirs(p, exist_ok=True)
def daydir():
    p=os.path.join(LOG_ROOT,day()); mkdir(os.path.join(p,'symbols')); return p
def sfn(s): return ''.join(c if c.isalnum() or c in '_-.' else '_' for c in str(s))

def load_state():
    global STATE
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH,'r',encoding='utf-8') as f: STATE.update(json.load(f))
        except Exception: pass

def save_state():
    with open(STATE_PATH,'w',encoding='utf-8') as f: json.dump(STATE,f,ensure_ascii=False,indent=2)
load_state()

def append_csv(path, header, row):
    mkdir(os.path.dirname(path)); exists=os.path.exists(path)
    with open(path,'a',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=header)
        if not exists: w.writeheader()
        w.writerow(row)

def log_summary(a):
    h=['time','symbol','name','price','ai_score','signal','buy_qty','sell_qty','market_mode','market_score','news_score','emergency_level','emergency_reason']
    append_csv(os.path.join(daydir(),f'summary_{day()}.csv'),h,a)

def log_symbol(a):
    h=['time','symbol','name','price','day_high','day_low','wma5','wma20','wma60','volume_ratio','change_pct','drop_from_high_pct','bounce_from_low_pct','ai_score','signal','market_score','news_score','emergency_level','emergency_reason','buy_ratio','buy_qty','sell_ratio','sell_qty','reason']
    name=sfn(a['name']); sym=sfn(a['symbol'])
    append_csv(os.path.join(daydir(),'symbols',f'{sym}_{name}.csv'),h,a)

def log_paper(row):
    h=['time','action','symbol','name','price','qty','cash','paper_total','realized_pnl','return_pct','reason']
    append_csv(os.path.join(daydir(),f'paper_trades_{day()}.csv'),h,row)

def log_real(row):
    h=['time','action','symbol','name','price','qty','result','order_id','message','reason']
    append_csv(os.path.join(daydir(),f'real_orders_{day()}.csv'),h,row)

class TossError(Exception): pass

def issue_token():
    if not TOSS_CLIENT_ID or not TOSS_CLIENT_SECRET: raise TossError('토스 환경변수 없음')
    r=requests.post('https://openapi.tossinvest.com/oauth2/token',data={'grant_type':'client_credentials','client_id':TOSS_CLIENT_ID,'client_secret':TOSS_CLIENT_SECRET},timeout=10)
    if r.status_code!=200: raise TossError(f'토스 토큰 실패 {r.status_code} {r.text}')
    j=r.json(); TOKEN['value']=j['access_token']; TOKEN['expires_at']=time.time()+int(j.get('expires_in',3600)); return TOKEN['value']

def headers(account=False):
    if not TOKEN['value'] or time.time()>TOKEN['expires_at']-60: issue_token()
    h={'Authorization':'Bearer '+TOKEN['value']}
    if account:
        seq=TOSS_ACCOUNT or LATEST.get('account_seq') or account_seq()
        h['X-Tossinvest-Account']=str(seq)
    return h

def g(path, params=None, account=False):
    r=requests.get('https://openapi.tossinvest.com'+path,params=params,headers=headers(account),timeout=10)
    if r.status_code!=200: raise TossError(f'GET {path} {r.status_code} {r.text}')
    return r.json().get('result')

def p(path, payload=None, account=False):
    r=requests.post('https://openapi.tossinvest.com'+path,json=payload or {},headers=headers(account),timeout=10)
    if r.status_code!=200: raise TossError(f'POST {path} {r.status_code} {r.text}')
    return r.json().get('result')

def account_seq():
    if TOSS_ACCOUNT:
        LATEST['account_seq']=int(TOSS_ACCOUNT); return int(TOSS_ACCOUNT)
    arr=g('/api/v1/accounts')
    if not arr: raise TossError('계좌 없음')
    LATEST['account_seq']=arr[0]['accountSeq']; return arr[0]['accountSeq']

def prices(symbols):
    out={}
    for i in range(0,len(symbols),190):
        arr=g('/api/v1/prices',{'symbols':','.join(symbols[i:i+190])}) or []
        for x in arr: out[x['symbol']]={'price':fnum(x.get('lastPrice')),'currency':x.get('currency'),'timestamp':x.get('timestamp')}
    return out

def candles(sym):
    r=g('/api/v1/candles',{'symbol':sym,'interval':'1m','count':80,'adjusted':'true'}) or {}
    arr=r.get('candles',[]); arr.sort(key=lambda x:x.get('timestamp','')); return arr

def holdings(): return g('/api/v1/holdings',account=True) or {}
def bp(cur='KRW'):
    try: return fnum((g('/api/v1/buying-power',{'currency':cur},account=True) or {}).get('cashBuyingPower'))
    except Exception: return 0
def fx():
    try: return fnum((g('/api/v1/exchange-rate',{'baseCurrency':'USD','quoteCurrency':'KRW'}) or {}).get('rate'))
    except Exception: return 0
def sellable(sym):
    try: return inum((g('/api/v1/sellable-quantity',{'symbol':sym},account=True) or {}).get('sellableQuantity'))
    except Exception: return 0

def order(sym,side,qty):
    if not ALLOW_REAL_ORDERS: raise TossError('ALLOW_REAL_ORDERS=false')
    if qty<=0: raise TossError('수량 0')
    payload={'clientOrderId':f'mw-{int(time.time())}-{sym}-{side}'[:36],'symbol':sym,'side':side,'orderType':'MARKET','quantity':str(int(qty))}
    return p('/api/v1/orders',payload,account=True)

def send_kakao(text):
    if not KAKAO_TOKEN: return False,'KAKAO_TOKEN 없음'
    tpl={'object_type':'text','text':text[:900],'link':{'web_url':APP_URL or 'https://developers.kakao.com','mobile_web_url':APP_URL or 'https://developers.kakao.com'}}
    try:
        r=requests.post('https://kapi.kakao.com/v2/api/talk/memo/default/send',headers={'Authorization':'Bearer '+KAKAO_TOKEN,'Content-Type':'application/x-www-form-urlencoded;charset=utf-8'},data={'template_object':json.dumps(tpl,ensure_ascii=False)},timeout=10)
        msg=f'HTTP {r.status_code} {r.text}'; STATE['last_kakao']=nts()+' '+msg; save_state(); return r.status_code==200,msg
    except Exception as e:
        STATE['last_kakao']=nts()+' '+str(e); save_state(); return False,str(e)

def check_kakao():
    r=requests.get('https://kapi.kakao.com/v2/user/me',headers={'Authorization':'Bearer '+KAKAO_TOKEN},timeout=10)
    return r.status_code==200,f'HTTP {r.status_code}\n{r.text}'

GOOD=['수주','실적','호실적','상향','HBM','엔비디아','AI','계약','강세','반등','최대','흑자']
BAD=['급락','하락','쇼크','부진','둔화','제재','규제','전쟁','금리','환율 급등','목표가 하향','적자','감산']
QUERIES=['SK하이닉스','삼성전자 반도체','HBM 엔비디아','코스피 반도체','미국 증시 반도체','환율 금리 전쟁']

def news_score():
    if not ENABLE_NEWS: return 0,[]
    if time.time()-NEWS['ts']<NEWS_REFRESH_SEC: return NEWS['score'],NEWS['items']
    score=0; items=[]
    for q in QUERIES:
        try:
            url='https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=ko&gl=KR&ceid=KR:ko'
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            xml=urllib.request.urlopen(req,timeout=8).read(); root=ET.fromstring(xml)
            for it in root.findall('.//item')[:5]:
                title=it.findtext('title') or ''; low=title.lower(); s=0
                for w in GOOD:
                    if w.lower() in low: s+=1
                for w in BAD:
                    if w.lower() in low: s-=1
                score+=s; items.append({'query':q,'title':title,'score':s})
        except Exception: pass
    score=max(-20,min(20,score*2)); NEWS.update({'ts':time.time(),'score':score,'items':items[:12]}); return score,items[:12]

def wma(vals,n):
    vals=[fnum(x) for x in vals]
    if not vals: return 0
    if len(vals)<n: return vals[-1]
    r=vals[-n:]; ws=range(1,n+1); return sum(v*w for v,w in zip(r,ws))/sum(ws)

def metrics(cs, fallback=0):
    closes=[fnum(c.get('closePrice')) for c in cs]; highs=[fnum(c.get('highPrice')) for c in cs]; lows=[fnum(c.get('lowPrice')) for c in cs]; vols=[fnum(c.get('volume')) for c in cs]
    price=closes[-1] if closes else fallback; high=max(highs) if highs else price; low=min(lows) if lows else price
    avg=sum(vols[-21:-1])/max(1,len(vols[-21:-1])) if len(vols)>2 else (vols[-1] if vols else 0); cur=vols[-1] if vols else 0
    return {'price':price,'day_high':high,'day_low':low,'wma5':wma(closes,5),'wma20':wma(closes,20),'wma60':wma(closes,60),'volume_ratio':cur/avg if avg else 0,'change_pct':((closes[-1]-closes[-2])/closes[-2]*100) if len(closes)>1 and closes[-2] else 0,'drop_from_high_pct':((price-high)/high*100) if high else 0,'bounce_from_low_pct':((price-low)/low*100) if low else 0}

def market_score(ana, ns):
    score=50; lev=ana.get('122630',{}); inv=ana.get('252670',{})
    if lev.get('wma5',0)>lev.get('wma20',0)>lev.get('wma60',0): score+=15
    if lev.get('change_pct',0)>0: score+=5
    if inv.get('wma5',0)>inv.get('wma20',0): score-=12
    if inv.get('change_pct',0)>0: score-=5
    score+=max(-10,min(10,ns/2)); score=max(0,min(100,score))
    return score, '강세' if score>=70 else ('보통' if score>=55 else ('약세/관망' if score>=40 else '방어'))

def ai(sym,m,ms,ns):
    kind=SMAP.get(sym,{}).get('kind','stock'); score=50; rs=[]; price=m['price']; w5=m['wma5']; w20=m['wma20']; w60=m['wma60']; vol=m['volume_ratio']; chg=m['change_pct']; drop=m['drop_from_high_pct']; bounce=m['bounce_from_low_pct']
    if price>w5>w20: score+=18; rs.append('단기 상승 정렬')
    elif price>w5: score+=8; rs.append('단기선 회복')
    elif price<w5<w20: score-=18; rs.append('단기 하락 정렬')
    score += 8 if w20>w60 else -5
    if vol>=1.8 and chg>0: score+=8; rs.append('거래량 동반 상승')
    if vol>=1.8 and chg<0: score-=12; rs.append('거래량 동반 하락')
    if drop<=-3: score-=10; rs.append('고점 대비 급락')
    if bounce>=1.5 and price>w5: score+=5; rs.append('저점 반등')
    if 'inverse' in kind: score+=(50-ms)*0.35-ns*0.15
    else: score+=(ms-50)*0.35+ns*0.15
    score=max(0,min(100,score))
    if score>=85: return score,'강한 진입',0.70,' / '.join(rs[:4])
    if score>=75: return score,'진입 후보',0.50,' / '.join(rs[:4])
    if score>=65: return score,'소액 후보',0.30,' / '.join(rs[:4])
    if score<=40: return score,'매도/방어',0.0,' / '.join(rs[:4])
    return score,'관망',0.0,' / '.join(rs[:4])

def emergency(m,score,ms,ns):
    drop=m['drop_from_high_pct']; vol=m['volume_ratio']
    if drop<=-4.5 and vol>=1.8 and score<=40 and (ms<=35 or ns<=-8): return 3,f'강한 비상: 고점대비 {drop:.2f}%, 거래량 {vol:.2f}배, AI {score:.0f}'
    if drop<=-3.5 and vol>=1.8 and score<=45: return 2,f'부분 비상: 고점대비 {drop:.2f}%, 거래량 {vol:.2f}배, AI {score:.0f}'
    if drop<=-2.5: return 1,f'경고: 고점대비 {drop:.2f}%'
    return 0,''

def holdmap(h):
    out={}
    for x in h.get('items',[]): out[x['symbol']]={'qty':inum(x.get('quantity')),'name':x.get('name',x['symbol'])}
    return out

def total_asset(h,bkrw,busd,rate):
    mv=h.get('marketValue',{}).get('amount',{}) if h else {}; return bkrw + fnum(mv.get('krw')) + (busd+fnum(mv.get('usd')))*rate if rate else bkrw+fnum(mv.get('krw'))

def paper_total(pr):
    total=fnum(STATE.get('paper_cash'))
    for s,pos in STATE.get('paper_positions',{}).items(): total+=inum(pos.get('qty'))*pr.get(s,{}).get('price',0)
    return total

def paper_buy(sym,price,ratio,reason):
    if STATE.get('paper_cash') is None or price<=0 or ratio<=0: return
    cash=fnum(STATE['paper_cash']); qty=int((cash*ratio)//price)
    if qty<=0: return
    pos=STATE['paper_positions'].get(sym,{'qty':0,'avg':0}); oq=inum(pos['qty']); avg=fnum(pos['avg']); cost=qty*price; nq=oq+qty; navg=(oq*avg+cost)/nq
    STATE['paper_cash']=cash-cost; STATE['paper_positions'][sym]={'qty':nq,'avg':navg}; total=paper_total(LATEST['prices']); ret=(total-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
    log_paper({'time':nts(),'action':'가상매수','symbol':sym,'name':SMAP.get(sym,{}).get('name',sym),'price':price,'qty':qty,'cash':STATE['paper_cash'],'paper_total':total,'realized_pnl':STATE['paper_realized'],'return_pct':ret,'reason':reason})

def paper_sell(sym,price,ratio,reason):
    pos=STATE.get('paper_positions',{}).get(sym)
    if not pos or price<=0 or ratio<=0: return
    have=inum(pos['qty']); qty=have if ratio>=1 else max(1,int(have*ratio)); avg=fnum(pos['avg']); pnl=(price-avg)*qty
    STATE['paper_cash']=fnum(STATE['paper_cash'])+qty*price; STATE['paper_realized']=fnum(STATE['paper_realized'])+pnl
    if have-qty<=0: STATE['paper_positions'].pop(sym,None)
    else: STATE['paper_positions'][sym]={'qty':have-qty,'avg':avg}
    total=paper_total(LATEST['prices']); ret=(total-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
    log_paper({'time':nts(),'action':'가상매도','symbol':sym,'name':SMAP.get(sym,{}).get('name',sym),'price':price,'qty':qty,'cash':STATE['paper_cash'],'paper_total':total,'realized_pnl':STATE['paper_realized'],'return_pct':ret,'reason':reason})

def run_paper(ana):
    if STATE.get('paper_start') is None: return
    for s,a in ana.items():
        if s in STATE.get('paper_positions',{}):
            if a['emergency_level']>=3 or a['ai_score']<=40: paper_sell(s,a['price'],1.0,'AI 가상 방어/비상 매도')
            elif a['emergency_level']==2 or a['ai_score']<=45: paper_sell(s,a['price'],0.5,'AI 가상 분할매도')
    c=[a for a in ana.values() if a['buy_ratio']>0 and a['emergency_level']==0 and a['symbol'] not in STATE.get('paper_positions',{})]
    if c:
        b=sorted(c,key=lambda x:x['ai_score'],reverse=True)[0]; paper_buy(b['symbol'],b['price'],b['buy_ratio'],f"AI 가상 {b['signal']} {b['reason']}")

def update_once():
    try:
        account_seq(); syms=[x['symbol'] for x in SYMBOLS]; pr=prices(syms); h=holdings(); hm=holdmap(h); bkrw=bp('KRW'); busd=bp('USD'); rate=fx(); tot=total_asset(h,bkrw,busd,rate); ns,ni=news_score()
        raw={}
        for s in syms:
            try: raw[s]=metrics(candles(s),pr.get(s,{}).get('price',0))
            except Exception: raw[s]=metrics([],pr.get(s,{}).get('price',0))
        ms,mm=market_score(raw,ns); ana={}; maxem={'level':0,'reason':''}
        for s,m in raw.items():
            sc,sg,br,reason=ai(s,m,ms,ns); lev,er=emergency(m,sc,ms,ns); held=hm.get(s,{}).get('qty',0); se=sellable(s) if held>0 else 0
            price=m['price']; bq=int((bkrw*br)//price) if br and price>0 else 0
            sr=1.0 if lev>=3 or sc<=35 else (0.5 if lev==2 or sc<=45 else (0.3 if sc<=55 else 0.0)); sq=int(se*sr) if se else 0
            a={**m,'time':nts(),'symbol':s,'name':SMAP.get(s,{}).get('name',s),'ai_score':sc,'signal':sg,'market_score':ms,'news_score':ns,'emergency_level':lev,'emergency_reason':er,'buy_ratio':br,'buy_qty':bq,'sell_ratio':sr,'sell_qty':sq,'held_qty':held,'sellable_qty':se,'reason':reason}
            ana[s]=a; log_symbol(a); log_summary({k:a.get(k,'') for k in ['time','symbol','name','price','ai_score','signal','buy_qty','sell_qty','market_score','news_score','emergency_level','emergency_reason']}|{'market_mode':mm})
            if lev>maxem['level']: maxem={'level':lev,'reason':er}
        with LOCK:
            LATEST.update({'updated_at':nts(),'total_asset':tot,'buying_power_krw':bkrw,'holdings':h.get('items',[]),'prices':pr,'analysis':ana,'market_score':ms,'market_mode':mm,'news_score':ns,'news_items':ni,'emergency':maxem})
            LATEST['real_return']=(tot-fnum(STATE['real_base']))/fnum(STATE['real_base'])*100 if STATE.get('real_base') else 0
            LATEST['paper_total']=paper_total(pr); LATEST['paper_return']=(LATEST['paper_total']-fnum(STATE['paper_start']))/fnum(STATE['paper_start'])*100 if STATE.get('paper_start') else 0
            run_paper(ana); save_state()
        emergency_real_sell(ana)
    except Exception as e:
        STATE['last_error']=nts()+' '+str(e); save_state()

def emergency_real_sell(ana):
    if not (ALLOW_REAL_ORDERS and ENABLE_EMERGENCY_AUTO_SELL): return
    for s,a in ana.items():
        if a['emergency_level']<2 or a['sellable_qty']<=0 or a['price']<=0: continue
        if time.time()-STATE.get('last_emergency_sell',{}).get(s,0)<EMERGENCY_COOLDOWN_SEC: continue
        qty=a['sellable_qty'] if a['emergency_level']>=3 else max(1,int(a['sellable_qty']*0.5))
        try:
            r=order(s,'SELL',qty); STATE.setdefault('last_emergency_sell',{})[s]=time.time(); save_state(); send_kakao(f"🚨 비상 자동매도 실행\n{a['name']} {qty}주\n{a['emergency_reason']}"); log_real({'time':nts(),'action':'비상자동매도','symbol':s,'name':a['name'],'price':a['price'],'qty':qty,'result':'SUCCESS','order_id':r.get('orderId',''),'message':json.dumps(r,ensure_ascii=False),'reason':a['emergency_reason']})
        except Exception as e:
            send_kakao(f"🚨 비상 자동매도 실패\n{a['name']}\n{e}"); log_real({'time':nts(),'action':'비상자동매도','symbol':s,'name':a['name'],'price':a['price'],'qty':qty,'result':'FAIL','order_id':'','message':str(e),'reason':a['emergency_reason']})

def worker():
    while True:
        update_once(); time.sleep(max(10,REFRESH_SEC))

def page():
    em=LATEST['emergency']; cls='danger' if em['level']>=3 else ('warn' if em['level'] else 'ok')
    rows=''
    for a in sorted(LATEST['analysis'].values(),key=lambda x:x['ai_score'],reverse=True):
        rows+=f"""<tr class='{ 'dangerrow' if a['emergency_level']>=3 else ('warnrow' if a['emergency_level'] else '') }'><td><b>{esc(a['name'])}</b><br><small>{esc(a['symbol'])}</small></td><td>{won(a['price'])}<br><small>고점대비 {a['drop_from_high_pct']:.2f}%</small></td><td><b>{a['ai_score']:.0f}</b><br>{esc(a['signal'])}</td><td>{a['volume_ratio']:.2f}배</td><td>{int(a['buy_ratio']*100)}%<br>{a['buy_qty']:,}주</td><td>{int(a['sell_ratio']*100)}%<br>{a['sell_qty']:,}주</td><td>{a['held_qty']:,}주<br><small>매도가능 {a['sellable_qty']:,}</small></td><td>{esc(a['reason'])}<br><small>{esc(a['emergency_reason'])}</small></td><td><form method='post' action='/real_buy' onsubmit="return confirm('실계좌 매수 주문?')"><input type='hidden' name='symbol' value='{esc(a['symbol'])}'><input name='qty' value='{a['buy_qty']}'><button class='buy'>매수</button></form><form method='post' action='/real_sell' onsubmit="return confirm('실계좌 매도 주문?')"><input type='hidden' name='symbol' value='{esc(a['symbol'])}'><input name='qty' value='{a['sell_qty']}'><button class='sell'>매도</button></form></td></tr>"""
    news=''.join(f"<li>[{esc(x['query'])}] {esc(x['title'])} <b>{x['score']}</b></li>" for x in LATEST['news_items'][:10])
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='30'><title>Market Watch</title><style>body{{background:#08090d;color:white;font-family:Arial;padding:20px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{background:#141821;border:1px solid #2a2f3a;border-radius:14px;padding:18px;margin:12px 0}}.big{{font-size:30px;color:#ffe04a;font-weight:bold}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{border-bottom:1px solid #303642;padding:8px;vertical-align:top}}input{{width:70px;background:#0b0d12;color:white;border:1px solid #444;border-radius:6px;padding:5px}}button,.btn{{border:0;border-radius:8px;padding:8px 12px;margin:3px;color:white;text-decoration:none;background:#333;font-weight:bold}}.buy{{background:#e53e3e}}.sell{{background:#2563eb}}.purple{{background:#7c3aed}}.ok{{color:#47ff8a}}.warn{{color:#ffbf47}}.danger{{color:#ff4d4d}}.warnrow{{background:#251a08}}.dangerrow{{background:#2a0808}}small{{color:#aaa}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><h1>Market Watch 최종본</h1><div class='grid'><div class='card'><h2>실계좌</h2><div class='big'>{won(LATEST['total_asset'])}</div><p>기준금: {won(STATE['real_base']) if STATE.get('real_base') else '미설정'}</p><p>수익률: {pct(LATEST['real_return'])}</p><p>매수가능: {won(LATEST['buying_power_krw'])}</p><p>실주문: {'활성화' if ALLOW_REAL_ORDERS else '차단'}</p><form method='post' action='/reset_base' onsubmit="return confirm('현재 총자산으로 기준금과 AI가상 리셋?')"><button class='purple'>오늘 기준금/AI가상 리셋</button></form></div><div class='card'><h2>AI 가상계좌</h2><div class='big'>{won(LATEST['paper_total'])}</div><p>시작금: {won(STATE['paper_start']) if STATE.get('paper_start') else '미설정'}</p><p>현금: {won(STATE['paper_cash']) if STATE.get('paper_cash') is not None else '미설정'}</p><p>수익률: {pct(LATEST['paper_return'])}</p><p>실계좌 대비: {pct(LATEST['paper_return']-LATEST['real_return'])}p</p></div><div class='card'><h2>시장/비상</h2><p class='{cls}'>{'🚨 강한 비상' if em['level']>=3 else ('🟡 경고/부분비상' if em['level'] else '🟢 정상')}</p><p>{esc(em['reason'])}</p><p>시장: {esc(LATEST['market_mode'])} / {LATEST['market_score']:.0f}</p><p>뉴스: {LATEST['news_score']:.0f}</p><p>비상자동매도: {'ON' if ENABLE_EMERGENCY_AUTO_SELL else 'OFF'}</p><p>업데이트: {esc(LATEST['updated_at'])}</p></div></div><div class='card'><h2>종목별 AI 판단</h2><table><tr><th>종목</th><th>현재가</th><th>AI</th><th>거래량</th><th>추천매수</th><th>추천매도</th><th>보유</th><th>사유</th><th>실계좌</th></tr>{rows}</table></div><div class='grid'><div class='card'><h2>뉴스</h2><ul>{news}</ul></div><div class='card'><h2>테스트/저장</h2><p><a class='btn' href='/check_kakao'>카카오 토큰</a><a class='btn' href='/test_kakao'>카카오 테스트</a><a class='btn' href='/force_update'>즉시갱신</a></p><p><a class='btn' href='/download?type=summary'>오늘 요약 CSV</a><a class='btn' href='/download?type=paper'>AI 가상 CSV</a><a class='btn' href='/download?type=real'>실계좌 주문 CSV</a></p><p><a class='btn' href='/symbols_csv'>종목별 CSV 목록</a></p><p>카카오: {esc(STATE['last_kakao'])}</p><p>오류: <small>{esc(STATE['last_error'])}</small></p></div></div></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urlparse(self.path); path=u.path; qs=parse_qs(u.query)
        if path=='/': return self.html(page())
        if path=='/force_update': update_once(); return self.redir('/')
        if path=='/check_kakao': ok,msg=check_kakao(); return self.result('토큰 확인 성공' if ok else '토큰 확인 실패',msg)
        if path=='/test_kakao': ok,msg=send_kakao('✅ Market Watch 카카오톡 테스트 성공\n'+nts()); return self.result('카카오 전송 성공' if ok else '카카오 전송 실패',msg)
        if path=='/download':
            typ=qs.get('type',['summary'])[0]; d=daydir(); fn=f"summary_{day()}.csv" if typ=='summary' else (f"paper_trades_{day()}.csv" if typ=='paper' else f"real_orders_{day()}.csv"); return self.file(os.path.join(d,fn))
        if path=='/symbols_csv':
            d=os.path.join(daydir(),'symbols'); mkdir(d); links=''.join(f"<li><a href='/symbol_file?name={quote_plus(fn)}'>{esc(fn)}</a></li>" for fn in sorted(os.listdir(d))); return self.html('<h1>종목별 CSV</h1><ul>'+links+"</ul><a href='/'>돌아가기</a>")
        if path=='/symbol_file': return self.file(os.path.join(daydir(),'symbols',os.path.basename(qs.get('name',[''])[0])))
        if path=='/api/state': return self.json({'latest':LATEST,'state':STATE})
        return self.result('404','없는 주소')
    def do_POST(self):
        path=urlparse(self.path).path; data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length',0))).decode())
        if path=='/reset_base':
            update_once(); base=fnum(LATEST['total_asset']); STATE.update({'real_base':base,'paper_start':base,'paper_cash':base,'paper_positions':{},'paper_realized':0.0}); save_state(); log_paper({'time':nts(),'action':'AI가상리셋','symbol':'-','name':'-','price':0,'qty':0,'cash':base,'paper_total':base,'realized_pnl':0,'return_pct':0,'reason':'오늘 기준금/AI가상 리셋'}); send_kakao(f'✅ 오늘 기준금/AI가상 리셋\n기준금: {won(base)}\n{nts()}'); return self.redir('/')
        if path in ['/real_buy','/real_sell']:
            sym=data.get('symbol',[''])[0]; qty=inum(data.get('qty',['0'])[0]); side='BUY' if path.endswith('buy') else 'SELL'; a=LATEST['analysis'].get(sym,{}); name=SMAP.get(sym,{}).get('name',sym); price=a.get('price',0)
            try:
                if price<=0: raise TossError('현재가 0')
                r=order(sym,side,qty); msg=json.dumps(r,ensure_ascii=False); log_real({'time':nts(),'action':'실계좌매수' if side=='BUY' else '실계좌매도','symbol':sym,'name':name,'price':price,'qty':qty,'result':'SUCCESS','order_id':r.get('orderId',''),'message':msg,'reason':a.get('reason','')}); send_kakao(f"✅ 실계좌 {'매수' if side=='BUY' else '매도'} 주문\n{name}\n{qty}주"); return self.result('주문 성공',msg)
            except Exception as e:
                log_real({'time':nts(),'action':'실계좌매수' if side=='BUY' else '실계좌매도','symbol':sym,'name':name,'price':price,'qty':qty,'result':'FAIL','order_id':'','message':str(e),'reason':a.get('reason','')}); send_kakao(f"⚠️ 실계좌 주문 실패\n{name}\n{e}"); return self.result('주문 실패',str(e))
        return self.result('404','없는 POST')
    def html(self,s): self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(s.encode('utf-8'))
    def result(self,t,m): self.html(f"<html><meta charset='utf-8'><body style='background:#08090d;color:white;font-family:Arial;padding:30px'><h1>{esc(t)}</h1><pre style='background:#000;color:#00ff66;padding:15px;white-space:pre-wrap'>{esc(m)}</pre><a style='color:#ffe812;font-size:24px' href='/'>돌아가기</a></body></html>")
    def redir(self,p): self.send_response(302); self.send_header('Location',p); self.end_headers()
    def json(self,o): self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.end_headers(); self.wfile.write(json.dumps(o,ensure_ascii=False,default=str).encode())
    def file(self,p):
        if not os.path.exists(p): return self.result('파일 없음',p)
        self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8'); self.send_header('Content-Disposition','attachment; filename='+os.path.basename(p)); self.end_headers(); self.wfile.write(open(p,'rb').read())
    def log_message(self,*args): pass

if __name__=='__main__':
    print('Market Watch start',PORT,'ALLOW_REAL_ORDERS',ALLOW_REAL_ORDERS,'EMERGENCY_AUTO_SELL',ENABLE_EMERGENCY_AUTO_SELL)
    threading.Thread(target=worker,daemon=True).start()
    HTTPServer(('0.0.0.0',PORT),H).serve_forever()
