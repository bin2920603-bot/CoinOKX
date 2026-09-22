#!/usr/bin/env python3
"""OKX 선물(USDT 무기한) 전체 종목의 24시간 거래대금을 기록한다.
표 화면에 그대로 보이도록 업비트 USDT 가격으로 원화(억원)로 바꿔 저장한다."""
import json, os, time
from datetime import datetime, timedelta, timezone
import requests

# OKX 주소 (앞 주소가 막히면 다음 주소로 시도)
OKX_HOSTS = ["https://www.okx.com", "https://aws.okx.com"]

# 시총 순위가 엉뚱하게 잡히면 여기에 "OKX-A": "코인게코id" 형태로 고정
OVERRIDE = {}

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
VOL = os.path.join(ROOT, "data", "volumes.json")
CAP = os.path.join(ROOT, "data", "marketcap.json")
KEEP_DAYS = 7


def get(url, params=None, tries=4):
    for i in range(tries):
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 429:
            time.sleep(1.5 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def okx_tickers():
    """OKX 선물(무기한) 전체 시세. 막힌 주소는 건너뛰고 다음 주소로."""
    errors = []
    for host in OKX_HOSTS:
        try:
            j = get(host + "/api/v5/market/tickers", {"instType": "SWAP"})
            if j.get("code") != "0":
                raise RuntimeError(f"OKX 응답 오류: {j.get('code')} {j.get('msg')}")
            return j["data"]
        except Exception as e:
            errors.append(f"{host} -> {e}")
            print(f"  ! OKX 접속 실패: {host} -> {e}")
    raise RuntimeError("OKX에 접속하지 못했습니다:\n" + "\n".join(errors))


def usdt_krw():
    """업비트 테더(USDT) 원화 가격 = 환율로 사용"""
    t = get("https://api.upbit.com/v1/ticker", {"markets": "KRW-USDT"})
    return float(t[0]["trade_price"])


def korean_names():
    """업비트에 있는 코인은 한글 이름을 빌려 쓴다 (없으면 영문 기호)"""
    try:
        markets = get("https://api.upbit.com/v1/market/all", {"isDetails": "false"})
        return {m["market"].split("-", 1)[1]: m["korean_name"]
                for m in markets if m["market"].startswith("KRW-")}
    except Exception:
        return {}


def slot_now():
    """지금 시각을 15분 단위로 내림 (예: 02:37 -> 02:30)"""
    now = datetime.now(KST)
    return now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def collect_volumes():
    store = json.load(open(VOL, encoding="utf-8")) if os.path.exists(VOL) else {"coins": {}}
    slot = slot_now()

    rate = usdt_krw()
    names = korean_names()
    rows = [t for t in okx_tickers() if t["instId"].endswith("-USDT-SWAP")]

    coins = []
    for t in rows:
        sym = t["instId"].split("-")[0]
        try:
            last = float(t["last"] or 0)
            open24 = float(t["open24h"] or 0)
            # 선물은 거래량이 코인 개수로 나와서 가격을 곱해 USDT 거래대금으로 바꾼다
            vol_usdt = float(t["volCcy24h"] or 0) * last
        except ValueError:
            continue
        if vol_usdt <= 0:
            continue
        code = "OKX-" + sym
        name = names.get(sym, sym)
        coins.append({"market": code, "name": name})

        entry = store["coins"].setdefault(code, {"name": name, "slots": {}})
        entry["name"] = name
        entry["price"] = last
        entry["change"] = round((last - open24) / open24 * 100, 2) if open24 else 0
        entry["slots"][slot] = round(vol_usdt * rate)   # 원화로 바꿔 저장

    cut = (datetime.now(KST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M")
    for e in store["coins"].values():
        e["slots"] = {k: v for k, v in e["slots"].items() if k >= cut}

    store["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    store["usdt_krw"] = rate
    store["failed"] = []
    os.makedirs(os.path.dirname(VOL), exist_ok=True)
    json.dump(store, open(VOL, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{slot} 저장 · OKX {len(coins)}종목 · 환율 {rate:,.0f}원")
    return coins


def collect_marketcap(coins):
    if os.path.exists(CAP):
        try:
            prev = json.load(open(CAP, encoding="utf-8"))
            if datetime.now(KST) - datetime.fromisoformat(prev["updated_at"]) < timedelta(hours=12):
                print("시총 순위는 12시간 내 갱신됨 · 건너뜀")
                return
        except Exception:
            pass

    by_symbol, by_id = {}, {}
    for page in range(1, 5):
        rows = get("https://api.coingecko.com/api/v3/coins/markets",
                   {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": page})
        for c in rows:
            rank = c.get("market_cap_rank")
            if not rank:
                continue
            by_id[c["id"]] = rank
            s = (c["symbol"] or "").upper()
            if s not in by_symbol or rank < by_symbol[s]:
                by_symbol[s] = rank
        time.sleep(2)

    ranks = {}
    for meta in coins:
        code = meta["market"]
        rank = by_id.get(OVERRIDE[code]) if code in OVERRIDE else by_symbol.get(code.split("-", 1)[1])
        if rank:
            ranks[code] = rank

    os.makedirs(os.path.dirname(CAP), exist_ok=True)
    json.dump({"updated_at": datetime.now(KST).isoformat(timespec="seconds"), "ranks": ranks},
              open(CAP, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"시총 순위 {len(ranks)}개 저장")


if __name__ == "__main__":
    coins = collect_volumes()
    try:
        collect_marketcap(coins)
    except Exception as e:
        print(f"시총 수집 건너뜀: {e}")            j = get(host + "/api/v5/market/tickers", {"instType": "SPOT"})
            if j.get("code") != "0":
                raise RuntimeError(f"OKX 응답 오류: {j.get('code')} {j.get('msg')}")
            return j["data"]
        except Exception as e:
            errors.append(f"{host} -> {e}")
            print(f"  ! OKX 접속 실패: {host} -> {e}")
    raise RuntimeError("OKX에 접속하지 못했습니다:\n" + "\n".join(errors))


def usdt_krw():
    """업비트 테더(USDT) 원화 가격 = 환율로 사용"""
    t = get("https://api.upbit.com/v1/ticker", {"markets": "KRW-USDT"})
    return float(t[0]["trade_price"])


def korean_names():
    """업비트에 있는 코인은 한글 이름을 빌려 쓴다 (없으면 영문 기호)"""
    try:
        markets = get("https://api.upbit.com/v1/market/all", {"isDetails": "false"})
        return {m["market"].split("-", 1)[1]: m["korean_name"]
                for m in markets if m["market"].startswith("KRW-")}
    except Exception:
        return {}


def slot_now():
    """지금 시각을 15분 단위로 내림 (예: 02:37 -> 02:30)"""
    now = datetime.now(KST)
    return now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def collect_volumes():
    store = json.load(open(VOL, encoding="utf-8")) if os.path.exists(VOL) else {"coins": {}}
    slot = slot_now()

    rate = usdt_krw()
    names = korean_names()
    rows = [t for t in okx_tickers() if t["instId"].endswith("-USDT")]

    coins = []
    for t in rows:
        sym = t["instId"].split("-")[0]
        try:
            last = float(t["last"] or 0)
            open24 = float(t["open24h"] or 0)
            vol_usdt = float(t["volCcy24h"] or 0)   # 현물은 USDT 기준 거래대금
        except ValueError:
            continue
        if vol_usdt <= 0:
            continue
        code = "OKX-" + sym
        name = names.get(sym, sym)
        coins.append({"market": code, "name": name})

        entry = store["coins"].setdefault(code, {"name": name, "slots": {}})
        entry["name"] = name
        entry["price"] = last
        entry["change"] = round((last - open24) / open24 * 100, 2) if open24 else 0
        entry["slots"][slot] = round(vol_usdt * rate)   # 원화로 바꿔 저장

    cut = (datetime.now(KST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M")
    for e in store["coins"].values():
        e["slots"] = {k: v for k, v in e["slots"].items() if k >= cut}

    store["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    store["usdt_krw"] = rate
    store["failed"] = []
    os.makedirs(os.path.dirname(VOL), exist_ok=True)
    json.dump(store, open(VOL, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{slot} 저장 · OKX {len(coins)}종목 · 환율 {rate:,.0f}원")
    return coins


def collect_marketcap(coins):
    if os.path.exists(CAP):
        try:
            prev = json.load(open(CAP, encoding="utf-8"))
            if datetime.now(KST) - datetime.fromisoformat(prev["updated_at"]) < timedelta(hours=12):
                print("시총 순위는 12시간 내 갱신됨 · 건너뜀")
                return
        except Exception:
            pass

    by_symbol, by_id = {}, {}
    for page in range(1, 5):
        rows = get("https://api.coingecko.com/api/v3/coins/markets",
                   {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": page})
        for c in rows:
            rank = c.get("market_cap_rank")
            if not rank:
                continue
            by_id[c["id"]] = rank
            s = (c["symbol"] or "").upper()
            if s not in by_symbol or rank < by_symbol[s]:
                by_symbol[s] = rank
        time.sleep(2)

    ranks = {}
    for meta in coins:
        code = meta["market"]
        rank = by_id.get(OVERRIDE[code]) if code in OVERRIDE else by_symbol.get(code.split("-", 1)[1])
        if rank:
            ranks[code] = rank

    os.makedirs(os.path.dirname(CAP), exist_ok=True)
    json.dump({"updated_at": datetime.now(KST).isoformat(timespec="seconds"), "ranks": ranks},
              open(CAP, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"시총 순위 {len(ranks)}개 저장")


if __name__ == "__main__":
    coins = collect_volumes()
    try:
        collect_marketcap(coins)
    except Exception as e:
        print(f"시총 수집 건너뜀: {e}")
