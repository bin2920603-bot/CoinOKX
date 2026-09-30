#!/usr/bin/env python3
"""OKX 선물 5분봉 EMA(7·20·50·200)+VWAP100 정배열/역배열/early + 거래대금 급증(hot, 시장 평균 대비)을 data/ema5.json 에 저장한다."""
import json, os, statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from ema import get, ema, STABLE, VOL, KST

OUT = os.path.join(os.path.dirname(VOL), "ema5.json")
CROSS_LOOKBACK = 6   # 최근 5분봉 3개(15분) 안에 넘었으면 early 후보
MIN_GAP = 0.0005     # EMA7이 EMA20보다 최소 0.05% 위에 있어야 함
SLOPE_BARS = 3       # EMA20이 3개 봉 전보다 올라와 있어야 함
HOT_RISE = 0.02      # 24시간 거래대금이 직전 칸보다 최소 2%는 늘어야 hot 후보
HOT_OVER = 0.05      # 그리고 시장 전체 중앙값보다 5%p 이상 더 늘어야 hot
MIN_TURNOVER = 10_000_000_000   # 24시간 거래대금 100억원 미만 종목은 제외(원 단위)


def vwap(highs, lows, closes, vols, n=100):
    h, l, c, v = highs[-n:], lows[-n:], closes[-n:], vols[-n:]
    total = sum(v)
    if total == 0:
        return None
    return sum((h[i] + l[i] + c[i]) / 3 * v[i] for i in range(len(v))) / total


def classify5(highs, lows, closes, vols):
    if len(closes) < 210:
        return None
    e7 = ema(closes, 7)
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e200 = ema(closes, 200)
    vw = vwap(highs, lows, closes, vols, 100)
    if vw is None:
        return None
    last = closes[-1]

    if e7 > e20 > e50 > e200 and last > vw:
        return "up"
    if e7 < e20 < e50 < e200 and last < vw:
        return "down"

    if e7 > e20 and last > vw and last > e50:
        if (e7 - e20) / e20 < MIN_GAP:
            return None
        e20_prev = ema(closes[:-SLOPE_BARS], 20)
        if e20 <= e20_prev:
            return None
        for k in range(1, CROSS_LOOKBACK + 1):
            past = closes[:-k]
            if len(past) < 201:
                break
            if ema(past, 7) <= ema(past, 20):
                return "early"
    return None


def hot_coins(store):
    """직전 15분 칸 대비 24시간 거래대금 증가율이 '시장 전체 중앙값'보다 HOT_OVER 이상 높은 종목.
    반환: ({코드: 증가율%}, 시장 중앙값)"""
    now = datetime.now(KST)
    rises = {}
    for code, e in store.get("coins", {}).items():
        sym = code.split("-", 1)[1]
        if sym.upper() in STABLE:
            continue
        slots = e.get("slots", {})
        if len(slots) < 2:
            continue
        keys = sorted(slots)
        try:
            last_t = datetime.strptime(keys[-1], "%Y-%m-%dT%H:%M").replace(tzinfo=KST)
        except ValueError:
            continue
        if now - last_t > timedelta(minutes=45):
            continue   # 데이터가 오래됐으면 건너뜀
        cur, prev = slots[keys[-1]], slots[keys[-2]]
        if prev <= 0:
            continue
        rises[code] = ((cur - prev) / prev, prev)
    if len(rises) < 20:
        return {}, 0.0   # 표본이 너무 적으면 판단하지 않음
    med = statistics.median(r for r, _ in rises.values())
    hot = {}
    for code, (rise, prev) in rises.items():
        if prev < MIN_TURNOVER:
            continue
        if rise >= HOT_RISE and rise - med >= HOT_OVER:
            hot[code] = round(rise * 100, 1)
    return hot, med


def check(code):
    sym = code.split("-", 1)[1]
    if sym.upper() in STABLE:
        return code, None, False
    try:
        c = get("/api/v5/market/candles", {"instId": f"{sym}-USDT-SWAP", "bar": "5m", "limit": "300"})
        c = list(reversed(c))
        highs = [float(x[2]) for x in c]
        lows = [float(x[3]) for x in c]
        closes = [float(x[4]) for x in c]
        vols = [float(x[5]) for x in c]
        return code, classify5(highs, lows, closes, vols), False
    except Exception as e:
        print(f"  ! {sym}: {e}")
        return code, None, True


def main():
    store = json.load(open(VOL, encoding="utf-8"))
    coins = list(store["coins"].keys())
    hot, med = hot_coins(store)
    trend, fail = {}, 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for code, t, failed in ex.map(check, coins):
            fail += failed
            if t:
                trend[code] = t
    json.dump({"updated_at": datetime.now(KST).isoformat(timespec="seconds"), "trend": trend, "hot": hot},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    up = sum(1 for v in trend.values() if v == "up")
    down = sum(1 for v in trend.values() if v == "down")
    early = sum(1 for v in trend.values() if v == "early")
    print(f"5분봉 정배열 {up} · 역배열 {down} · 넘는중 {early} · 거래대금급증 {len(hot)} (시장중앙값 {med*100:.1f}%) · 실패 {fail} / 전체 {len(coins)}")


if __name__ == "__main__":
    main()
