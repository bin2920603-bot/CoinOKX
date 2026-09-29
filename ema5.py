#!/usr/bin/env python3
"""OKX 선물 5분봉 EMA(5·20·60·120) 정배열/역배열 종목을 data/ema5.json 에 저장한다."""
import json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from ema import get, classify, STABLE, VOL, KST

OUT = os.path.join(os.path.dirname(VOL), "ema5.json")


def check(code):
    sym = code.split("-", 1)[1]
    if sym.upper() in STABLE:
        return code, None, False
    try:
        c = get("/api/v5/market/candles", {"instId": f"{sym}-USDT-SWAP", "bar": "5m", "limit": "300"})
        closes = [float(x[4]) for x in reversed(c)]
        return code, classify(closes), False
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
    print(f"5분봉 정배열 {up} · 역배열 {len(trend) - up} · 실패 {fail} / 전체 {len(coins)}")


if __name__ == "__main__":
    main()
