#!/usr/bin/env python3
"""15분 거래대금 기록과 별도로, 짧은 주기(2분)로 OKX 선물 가격만 체크해서
직전 체크 대비 급등한 종목을 감지·기록한다.

index.html이 기대하는 형식으로 저장한다:
  {"surges": {"OKX-BTC": {"level": 1, "pct": 12.3}, ...}, "updated_at": "..."}

level: 1 = 10~20% 상승, 2 = 20~50%, 3 = 50%~
"""
import json, os, time
from datetime import datetime, timedelta, timezone
import requests

# OKX 주소 (앞 주소가 막히면 다음 주소로 시도) — collect.py와 동일
OKX_HOSTS = ["https://www.okx.com", "https://aws.okx.com"]

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
SURGE = os.path.join(ROOT, "data", "surge.json")       # index.html이 읽는 파일
LAST = os.path.join(ROOT, "data", "surge_last.json")   # 직전 체크 시점 가격 스냅샷
ACTIVE_MIN = 20   # 급등 표시(배지)를 몇 분간 화면에 유지할지


def get(url, params=None, tries=3):
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


def level(pct):
    if pct >= 50:
        return 3
    if pct >= 20:
        return 2
    if pct >= 10:
        return 1
    return 0


def check():
    prices = {}
    for t in okx_tickers():
        if not t["instId"].endswith("-USDT-SWAP"):
            continue
        try:
            last = float(t["last"] or 0)
        except ValueError:
            continue
        if last <= 0:
            continue
        sym = t["instId"].split("-")[0]
        prices["OKX-" + sym] = last

    last = json.load(open(LAST, encoding="utf-8")) if os.path.exists(LAST) else {}

    prev = {"active": {}}
    if os.path.exists(SURGE):
        try:
            prev = json.load(open(SURGE, encoding="utf-8"))
        except Exception:
            pass
    prev_active = prev.get("active", {})

    now = datetime.now(KST)
    now_s = now.isoformat(timespec="seconds")
    cut = (now - timedelta(minutes=ACTIVE_MIN)).isoformat(timespec="seconds")

    # 아직 유효 시간이 지나지 않은 기존 급등은 유지
    active = {k: v for k, v in prev_active.items() if v.get("time", "") >= cut}

    new_count = 0
    for code, price in prices.items():
        prevp = last.get(code)
        if prevp:
            pct = (price - prevp) / prevp * 100
            lv = level(pct)
            if lv:
                active[code] = {"level": lv, "pct": round(pct, 1), "time": now_s}
                new_count += 1

    surges = {k: {"level": v["level"], "pct": v["pct"]} for k, v in active.items()}

    os.makedirs(os.path.dirname(SURGE), exist_ok=True)
    json.dump(
        {"surges": surges, "active": active, "updated_at": now_s},
        open(SURGE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":")
    )
    json.dump(prices, open(LAST, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    print(f"{now_s} 급등체크 · {len(prices)}종목 조회 · 신규 {new_count}건 · 표시중 {len(surges)}건")


if __name__ == "__main__":
    check()
