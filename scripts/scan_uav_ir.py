#!/usr/bin/env python3
"""无人机红外设备板块扫描:9只=热像仪4+无人机3+红外材料1+镜头1"""
import json, os, datetime
import tushare as ts

TARGETS = [
    # 红外热像仪整机
    ("002414.SZ", "002414.SHE", "高德红外", "红外热像仪+无人机", "红外热像仪#1+chufei无人机导弹"),
    ("688002.SH", "688002.SHG", "睿创微纳", "非制冷红外焦平面", "非制冷探测器+整机双龙头"),
    ("300516.SZ", "300516.SHE", "久之洋", "红外+激光光电", "中船系红外+激光光电"),
    ("002214.SZ", "002214.SHE", "大立科技", "非制冷探测器", "非制冷红外焦平面+整机"),
    # 无人机平台
    ("688070.SH", "688070.SHG", "纵横股份", "工业级无人机", "工业级无人机#1"),
    ("002389.SZ", "002389.SHE", "航天彩虹", "彩虹无人机", "军工无人机出口龙头"),
    ("688297.SH", "688297.SHG", "中无人机", "翼龙无人机", "中航系大型无人机"),
    # 红外材料/器件
    ("002428.SZ", "002428.SHE", "云南锗业", "锗材料(红外)", "锗材料#1,红外器件原料"),
    # 红外镜头
    ("300691.SZ", "300691.SHE", "联合光电", "红外镜头", "红外镜头+光电系统"),
]

def main():
    token = open(os.path.expanduser("~/.tushare_token")).read().strip()
    ts.set_token(token)
    pro = ts.pro_api()

    end = "20260819"
    for d in ["20260819", "20260818", "20260815", "20260814", "20260813"]:
        t = pro.daily(ts_code="000001.SZ", trade_date=d)
        if t is not None and len(t) > 0:
            end = d
            break
    print(f"Using trade_date: {end}")
    start_1y = "20250819"

    out = []
    for ts_code, eodhd_sym, name, sub, desc in TARGETS:
        print(f"=== {ts_code} {name} ===")
        try:
            df = ts.pro_bar(ts_code=ts_code, start_date=start_1y, end_date=end, adj="qfq")
            if df is None or len(df) == 0:
                df_d = pro.daily(ts_code=ts_code, start_date=start_1y, end_date=end)
                df_a = pro.adj_factor(ts_code=ts_code, start_date=start_1y, end_date=end)
                if df_d is None or len(df_d) == 0:
                    print(f"  SKIP {ts_code}: no data")
                    continue
                df_d = df_d.sort_values("trade_date").reset_index(drop=True)
                df_a = df_a.sort_values("trade_date").reset_index(drop=True)
                latest_adj = df_a["adj_factor"].iloc[0]
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
                print(f"  SKIP {ts_code}: only {len(qfq_closes)} bars")
                continue
            print(f"  bars: {len(qfq_closes)} last_date: {qfq_closes[-1]['date']}")
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        last = qfq_closes[-1]["close"]
        last_date = qfq_closes[-1]["date"]
        closes = [x["close"] for x in qfq_closes]

        win = qfq_closes[-120:] if len(qfq_closes) >= 120 else qfq_closes
        win_high = max([x["high"] for x in win])
        win_low = min([x["low"] for x in win])
        range_pos = (last - win_low) / (win_high - win_low) * 100 if win_high > win_low else 50
        pct_off_high = (last - win_high) / win_high * 100

        ret_1m = (closes[-1] / closes[-22] - 1) * 100 if len(closes) >= 22 else 0
        ret_3m = (closes[-1] / closes[-66] - 1) * 100 if len(closes) >= 66 else 0

        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
        above_sma50 = last > sma50

        if range_pos > 80 and ret_1m > 20:
            stage = "extended/parabolic"
        elif ret_1m > 15 and above_sma50:
            stage = "early-uptrend"
        elif range_pos < 40 or ret_3m < -15:
            stage = "downtrend/basing"
        else:
            stage = "range/neutral"

        pe_ttm = pb = total_mv_yi = None
        try:
            for d in [end, "20260818", "20260815", "20260814"]:
                bdf = pro.daily_basic(ts_code=ts_code, trade_date=d,
                                      fields="ts_code,close,pe_ttm,pb,total_mv,circ_mv")
                if bdf is not None and len(bdf) > 0:
                    break
            if bdf is not None and len(bdf) > 0:
                b = bdf.iloc[0].to_dict()
                pe_ttm = b.get("pe_ttm")
                pb = b.get("pb")
                total_mv = b.get("total_mv")
                total_mv_yi = float(total_mv) / 10000 if total_mv else None
        except Exception as e:
            print(f"  basic ERROR: {e}")

        eps_growth = rev_growth = None
        peg = None
        try:
            for period in ["20251231", "20250930", "20250630", "20260331"]:
                fdf = pro.fina_indicator(ts_code=ts_code, period=period,
                                         fields="ts_code,end_date,basic_eps_yoy,dt_netprofit_yoy,tr_yoy,or_yoy,netprofit_yoy")
                if fdf is not None and len(fdf) > 0:
                    r = fdf.iloc[0].to_dict()
                    eps_growth = r.get("dt_netprofit_yoy") if r.get("dt_netprofit_yoy") is not None else r.get("basic_eps_yoy")
                    rev_growth = r.get("tr_yoy")
                    if eps_growth is None:
                        eps_growth = r.get("netprofit_yoy")
                    print(f"  fina period={period} eps={eps_growth} rev={rev_growth}")
                    break
            if pe_ttm and eps_growth and eps_growth > 0:
                peg = round(pe_ttm / eps_growth, 2)
        except Exception as e:
            print(f"  fina ERROR: {e}")

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
        print(f"  -> last={rec['last']} stage={stage} rng={rec['range_pos_6mo_pct']}% 1m={rec['ret_1m_pct']}% 3m={rec['ret_3m_pct']}% pe={rec['trailing_pe']} pb={rec['pb']} mv={rec['total_mv_yi']} eps+={rec['eps_growth']} rev+={rec['rev_growth']} peg={peg}")

    out_path = "/workspace/tracking/_scan_无人机红外_CN.json"
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(out)} records to {out_path}")

if __name__ == "__main__":
    main()
