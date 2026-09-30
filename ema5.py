#!/usr/bin/env python3
"""OKX 선물 5분봉 EMA(7·20·50·200)+VWAP100 정배열/역배열 + 'EMA7이 EMA20을 막 넘은' 종목을 data/ema5.json 에 저장한다."""
import json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from ema import get, ema, STABLE, VOL, KST

OUT = os.path.join(os.path.dirname(VOL), "ema5.json")
CROSS_LOOKBACK = 3  # 최근 5분봉 3개(15분) 안에 넘었으면 early


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

    # 1) 이미 완성된 배열
    if e7 > e20 > e50 > e200 and last > vw:
        return "up"
    if e7 < e20 < e50 < e200 and last < vw:
        return "down"

    # 2) 막 넘은 종목: 지금은 7이 20 위인데, 최근 3개 봉 중에는 7이 20 아래였던 때가 있음
    if e7 > e20 and last > vw:
        for k in range(1, CROSS_LOOKBACK + 1):
            past = closes[:-k]
            if len(past) < 201:
                break
            if ema(past, 7) <= ema(past, 20):
                return "early"
    return None


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
    coins = list(json.load(open(VOL, encoding="utf-8"))["coins"].keys())
    trend, fail = {}, 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for code, t, failed in ex.map(check, coins):
            fail += failed
            if t:
                trend[code] = t
    json.dump({"updated_at": datetime.now(KST).isoformat(timespec="seconds"), "trend": trend},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    up = sum(1 for v in trend.values() if v == "up")
    down = sum(1 for v in trend.values() if v == "down")
    early = sum(1 for v in trend.values() if v == "early")
    print(f"5분봉 정배열 {up} · 역배열 {down} · 넘는중 {early} · 실패 {fail} / 전체 {len(coins)}")


if __name__ == "__main__":
    main()
