#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 FundamentalFilter 功能"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundamental_filter import FundamentalFilter

def test_filter():
    ff = FundamentalFilter(max_price=350.0, max_pe=100.0)

    # 1. 模拟极端高股价股票 (如茅台现价 1500元 > 350)
    fake_klines_high_price = [["2026-08-19", 1400, 1500, 1520, 1390, 10000]] * 260
    res1 = ff.inspect("600519", fake_klines_high_price, quote={"price": 1500.0, "pe": 25.0})
    assert not res1["passed"], "极端高股价(>350)应该被剔除"
    print("Test 1 (极端高股价>350剔除) passed ✅:", res1["action_suggest"])

    # 1b. 模拟合理白马股 (如现价 160元 <= 350)
    fake_klines_med_price = []
    price_med = 120.0
    for i in range(260):
        if i > 10: price_med *= 1.001
        fake_klines_med_price.append([f"2026-{i:03d}", price_med, price_med, price_med*1.01, price_med*0.99, 10000])
    res1b = ff.inspect("603259", fake_klines_med_price, quote={"price": 160.0, "pe": 35.0})
    assert res1b["passed"], "160元股票在限价350下应该通过"
    print("Test 1b (160元股票在限价350下正常通过) passed ✅:", res1b["action_suggest"])

    # 2. 模拟超高PE股票 (如 PE 150)
    fake_klines_normal = [["2026-08-19", 20, 25, 26, 19, 10000]] * 260
    res2 = ff.inspect("000001", fake_klines_normal, quote={"price": 25.0, "pe": 150.0})
    assert not res2["passed"], "超高PE应该被剔除"
    print("Test 2 (超高PE剔除) passed ✅:", res2["action_suggest"])

    # 3. 模拟亏损股 (PE <= 0)
    res3 = ff.inspect("000002", fake_klines_normal, quote={"price": 25.0, "pe": -10.0})
    assert not res3["passed"], "亏损股票应该被剔除"
    print("Test 3 (亏损股剔除) passed ✅:", res3["action_suggest"])

    # 4. 模拟长期阴跌股票 (从100跌到40, 回撤60%)
    klines_downtrend = []
    price = 100.0
    for i in range(260):
        if i > 10:
            price *= 0.996  # 持续阴跌
        klines_downtrend.append([f"2026-{i:03d}", price, price, price*1.01, price*0.99, 10000])
    res4 = ff.inspect("000003", klines_downtrend, quote={"price": price, "pe": 15.0})
    assert not res4["passed"], "长期阴跌应该被剔除"
    print("Test 4 (长期阴跌剔除) passed ✅:", res4["action_suggest"])

    # 5. 模拟正常合规股票 (股价35, PE 20, 稳健上涨)
    klines_good = []
    price = 20.0
    for i in range(260):
        if i > 10:
            price *= 1.002  # 稳健上涨
        klines_good.append([f"2026-{i:03d}", price, price, price*1.01, price*0.99, 10000])
    res5 = ff.inspect("000004", klines_good, quote={"price": price, "pe": 20.0})
    assert res5["passed"], "正常股票应该通过"
    print("Test 5 (优质股票正常通过) passed ✅:", res5["action_suggest"])

    print("\n所有测试全部顺利通过！🎉")

if __name__ == "__main__":
    test_filter()
