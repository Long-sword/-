#!/usr/bin/env python3
"""硅片板块扫描:直接用tushare库拉数据,计算stage/估值/增长,输出_scan_硅片.json"""
import json, os, datetime
import tushare as ts

# 8只硅片标的
TARGETS = [
    ("688126.SH", "688126.SHG", "沪硅产业", "大硅片12寸", "12英寸大硅片龙头+SOI"),
    ("605358.SH", "605358.SHG", "立昂微", "大硅片12寸", "12寸硅片+砷化镓"),
    ("002129.SZ", "002129.SHE", "TCL中环", "大硅片+光伏", "大尺寸硅片+光伏硅片"),
    ("688209.SH", "688209.SHG", "有研硅", "区熔硅片", "区熔硅片+8寸重掺"),
    ("003016.SZ", "003016.SHE", "中晶科技", "硅抛光片", "硅抛光片+非磁器件"),
    ("688584.SH", "688584.SHG", "上海合晶", "硅外延片", "硅外延片龙头+12寸"),
    ("300345.SZ", "300345.SHE", "华民股份", "硅片转型", "硅锰转型硅片"),
    ("603938.SH", "603938.SHG", "三孚股份", "硅片原料", "三氯氢硅(硅片原料)"),
]

def main():
    token = open(os.path.expanduser("~/.tushare_token")).read().strip()
    ts.set_token(token)
    pro = ts.pro_api()

    end = "20260814"
    start_6mo = "20260214"
    start_1y = "20250814"  # 拉长到1年,保证至少120个交易日

    out = []
    for ts_code, eodhd_sym, name, sub, desc in TARGETS:
        print(f"=== {ts_code} {name} ===")
        # 拉历史日线(qfq)
        try:
            df = ts.pro_bar(ts_code=ts_code, start_date=start_1y, end_date=end, adj="qfq")
            if df is None or len(df) == 0:
                # pro_bar可能权限不足,用daily+adj_factor手动算qfq
                df_d = pro.daily(ts_code=ts_code, start_date=start_1y, end_date=end)
                df_a = pro.adj_factor(ts_code=ts_code, start_date=start_1y, end_date=end)
                if df_d is None or len(df_d) == 0:
                    print(f"  SKIP {ts_code}: no daily data")
                    continue
                # 合并
                df_d = df_d.sort_values("trade_date").reset_index(drop=True)
                df_a = df_a.sort_values("trade_date").reset_index(drop=True)
                latest_adj = df_a["adj_factor"].iloc[0]  # 最新日期的adj
                qfq_closes = []
                for i in range(len(df_d)):
                    af = df_a["adj_factor"].iloc[i] if i < len(df_a) else latest_adj
                    qfq_closes.append({
                        "date": str(df_d["trade_date"].iloc[i]),
                        "close": float(df_d["close"].iloc[i]) * float(af) / float(latest_adj),
                        "high": float(df_d["high"].iloc[i]) * float(af) / float(latest_adj),
                        "low": float(df_d["low"].iloc[i]) * float(af) / float(latest_adj),
                    })
            else:
                df = df.sort_values("trade_date").reset_index(drop=True)
                qfq_closes = [{"date": str(r["trade_date"]), "close": float(r["close"]),
                               "high": float(r["high"]), "low": float(r["low"])}
                              for _, r in df.iterrows()]
            if len(qfq_closes) < 66:
                print(f"  SKIP {ts_code}: only {len(qfq_closes)} bars (<66)")
                continue
            print(f"  bars: {len(qfq_closes)}")
        except Exception as e:
            print(f"  ERROR {ts_code}: {e}")
            continue

        last = qfq_closes[-1]["close"]
        last_date = qfq_closes[-1]["date"]
        closes = [x["close"] for x in qfq_closes]

        # 6月区间(最近120交易日)
        win = qfq_closes[-120:] if len(qfq_closes) >= 120 else qfq_closes
        win_high = max([x["high"] for x in win])
        win_low = min([x["low"] for x in win])
        range_pos = (last - win_low) / (win_high - win_low) * 100 if win_high > win_low else 50
        pct_off_high = (last - win_high) / win_high * 100

        # 1月(22)/3月(66)动量
        ret_1m = (closes[-1] / closes[-22] - 1) * 100 if len(closes) >= 22 else 0
        ret_3m = (closes[-1] / closes[-66] - 1) * 100 if len(closes) >= 66 else 0

        # SMA50
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
        above_sma50 = last > sma50

        # stage
        if range_pos > 80 and ret_1m > 20:
            stage = "extended/parabolic"
        elif ret_1m > 15 and above_sma50:
            stage = "early-uptrend"
        elif range_pos < 40 or ret_3m < -15:
            stage = "downtrend/basing"
        else:
            stage = "range/neutral"

        # 估值 (daily_basic)
        try:
            bdf = pro.daily_basic(ts_code=ts_code, trade_date=end,
                                  fields="ts_code,close,pe_ttm,pb,total_mv,circ_mv")
            if bdf is None or len(bdf) == 0:
                # 试最近交易日
                for d in ["20260813", "20260812", "20260811", "20260808"]:
                    bdf = pro.daily_basic(ts_code=ts_code, trade_date=d,
                                          fields="ts_code,close,pe_ttm,pb,total_mv,circ_mv")
                    if bdf is not None and len(bdf) > 0:
                        break
            if bdf is not None and len(bdf) > 0:
                b = bdf.iloc[0].to_dict()
                pe_ttm = b.get("pe_ttm")
                pb = b.get("pb")
                total_mv = b.get("total_mv")  # 万元
                total_mv_yi = float(total_mv) / 10000 if total_mv else None
            else:
                pe_ttm = pb = total_mv_yi = None
        except Exception as e:
            print(f"  daily_basic ERROR: {e}")
            pe_ttm = pb = total_mv_yi = None

        # 财务指标 (fina_indicator 最新季报)
        eps_growth = rev_growth = None
        peg = None
        try:
            # 拉2025年报(20251231)和2024年报(20241231)
            for period in ["20251231", "20250930", "20250630"]:
                fdf = pro.fina_indicator(ts_code=ts_code, period=period,
                                         fields="ts_code,end_date,basic_eps_yoy,dt_netprofit_yoy,tr_yoy,or_yoy,netprofit_yoy,q_netprofit_yoy")
                if fdf is not None and len(fdf) > 0:
                    r = fdf.iloc[0].to_dict()
                    # 优先用dt_netprofit_yoy(扣非净利润增速)作为EPS代理,或basic_eps_yoy
                    eps_growth = r.get("dt_netprofit_yoy") if r.get("dt_netprofit_yoy") is not None else r.get("basic_eps_yoy")
                    rev_growth = r.get("tr_yoy")  # 营业总收入同比
                    if eps_growth is None:
                        eps_growth = r.get("netprofit_yoy")
                    print(f"  fina period={period} eps_growth={eps_growth} rev_growth={rev_growth}")
                    break
            if pe_ttm and eps_growth and eps_growth > 0:
                peg = round(pe_ttm / eps_growth, 2)
        except Exception as e:
            print(f"  fina_indicator ERROR: {e}")

        rec = {
            "ticker": eodhd_sym,
            "ts_code": ts_code,
            "name_zh": name,
            "sub_chain": sub,
            "desc": desc,
            "provider": "tushare(qfq)",
            "last": round(last, 2),
            "last_date": last_date,
            "range_pos_6mo_pct": round(range_pos, 0),
            "pct_off_6mo_high": round(pct_off_high, 1),
            "ret_1m_pct": round(ret_1m, 1),
            "ret_3m_pct": round(ret_3m, 1),
            "above_sma50": bool(above_sma50),
            "stage": stage,
            "low_6mo": round(win_low, 2),
            "high_6mo": round(win_high, 2),
            "trailing_pe": round(float(pe_ttm), 2) if pe_ttm else None,
            "pb": round(float(pb), 2) if pb else None,
            "total_mv_yi": round(total_mv_yi, 1) if total_mv_yi else None,
            "eps_growth": round(float(eps_growth), 1) if eps_growth is not None else None,
            "rev_growth": round(float(rev_growth), 1) if rev_growth is not None else None,
            "peg": peg,
        }
        out.append(rec)
        print(f"  -> last={rec['last']} stage={stage} pe={rec['trailing_pe']} pb={rec['pb']} mv={rec['total_mv_yi']} eps+={rec['eps_growth']} rev+={rec['rev_growth']} peg={peg}")

    out_path = "/workspace/tracking/_scan_硅片_CN.json"
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(out)} records to {out_path}")

if __name__ == "__main__":
    main()
