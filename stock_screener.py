"""
A股收盘/盘中选股脚本
策略:
  1. 首日大涨 + 次日小碎步
  2. 回踩20日线的前期强势股

推送方式（选一即可推送到个人微信）:
  --wechat-url <url>    企业微信群机器人
  --serverchan <key>     Server酱 (sct.ftqq.com)   ← 个人微信首选
  --pushplus <token>     PushPlus (pushplus.plus)

用法:
  python stock_screener.py                                    # 收盘后，仅存文件
  python stock_screener.py --intraday                         # 盘中模式
  python stock_screener.py --serverchan SCTxxxx               # 推送到个人微信
  python stock_screener.py --pushplus xxxxx
  python stock_screener.py --wechat-url https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
  python stock_screener.py --max-stocks 300                   # 仅分析前 N 只（按市值排序）
  python stock_screener.py --no-progress                      # 隐藏逐条进度
"""

import sys
import os
import json
import time
import random
from datetime import datetime, timedelta
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import pandas as pd
import numpy as np

# ====== 配置项 ======
TRADING_DAYS_NEEDED = 40
SURGE_THRESHOLD = 5.0          # 首日涨幅 >= 5%
MAX_PULLBACK_PCT = 2.0         # 偏离MA20不超过2%
VOLUME_RATIO = 1.5             # 首日量比 >= 1.5

today_str = datetime.now().strftime("%Y-%m-%d")
now_ts = datetime.now().strftime("%Y%m%d_%H%M")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def log(msg: str):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


# ====== 数据获取（绕过系统代理，用 curl_cffi）======
def _eastmoney_get(url: str, params: dict = None, timeout: int = 20, headers: dict = None):
    """用 curl_cffi 发请求，绕过系统代理"""
    from curl_cffi import requests as cr
    if headers is None:
        headers = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    else:
        headers.setdefault("User-Agent", UA)
        headers.setdefault("Accept-Encoding", "gzip, deflate")
    last_err = None
    for attempt in range(3):
        try:
            r = cr.get(
                url, params=params, timeout=timeout,
                impersonate="chrome120",
                headers=headers,
                proxies={},
            )
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            if attempt < 2:
                delay = 1.0 * (2 ** attempt) + random.uniform(0.5, 1.5)
                time.sleep(delay)
    raise last_err


# ====== 从三大交易所获取股票代码 ======
def _get_sse_stocks(symbol: str = "主板A股") -> list[dict]:
    """上海证券交易所股票列表"""
    indicator_map = {"主板A股": "1", "科创板": "8"}
    url = "https://query.sse.com.cn/sseQuery/commonQuery.do"
    headers = {
        "Referer": "https://www.sse.com.cn/assortment/stock/list/share/",
        "User-Agent": UA,
    }
    params = {
        "STOCK_TYPE": indicator_map[symbol],
        "REG_PROVINCE": "", "CSRC_CODE": "", "STOCK_CODE": "",
        "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
        "COMPANY_STATUS": "2,4,5,7,8",
        "type": "inParams", "isPagination": "true",
        "pageHelp.cacheSize": "1", "pageHelp.beginPage": "1",
        "pageHelp.pageSize": "10000", "pageHelp.pageNo": "1", "pageHelp.endPage": "1",
    }
    r = _eastmoney_get(url, params, headers=headers)
    data = r.json()
    results = data.get("pageHelp", {}).get("data", [])
    stocks = []
    for item in results:
        code = item.get("A_STOCK_CODE", "").strip()
        name = item.get("SEC_NAME_CN", "").strip()
        if code:
            stocks.append({"代码": code, "名称": name})
    return stocks


def _get_szse_stocks() -> list[dict]:
    """深圳证券交易所A股列表"""
    url = "https://www.szse.cn/api/report/ShowReport"
    params = {
        "SHOWTYPE": "xlsx",
        "CATALOGID": "1110",
        "TABKEY": "tab1",
        "random": str(random.random()),
    }
    r = _eastmoney_get(url, params)
    df = pd.read_excel(BytesIO(r.content))
    stocks = []
    for _, row in df.iterrows():
        code = str(row.get("A股代码", "")).strip()
        name = str(row.get("A股简称", "")).strip()
        ext = str(row.get("板块", "")).strip()
        if code and code != "nan":
            code = code.split(".")[0].zfill(6)
            stocks.append({"代码": code, "名称": name, "板块": ext})
    return stocks


def get_stock_list(max_stocks: int = 0) -> pd.DataFrame:
    """合并沪深北全部A股代码"""
    log("从上交所获取股票列表 ...")
    sse_main = _get_sse_stocks("主板A股")
    sse_kcb = _get_sse_stocks("科创板")
    sse_all = sse_main + sse_kcb
    log(f"  上交所 {len(sse_all)} 只")

    log("从深交所获取股票列表 ...")
    szse = _get_szse_stocks()
    log(f"  深交所 {len(szse)} 只")

    all_stocks = []
    seen = set()
    for s in sse_all + szse:
        code = s["代码"]
        if code not in seen:
            seen.add(code)
            all_stocks.append(s)

    log(f"合计 A 股 {len(all_stocks)} 只")
    df = pd.DataFrame(all_stocks)
    if max_stocks > 0 and len(df) > max_stocks:
        df = df.head(max_stocks)
        log(f"限制分析前 {max_stocks} 只（按列表顺序）")
    return df


# ====== 个股历史日线 ======
def get_history(symbol: str) -> pd.DataFrame | None:
    market_code = 1 if symbol.startswith("6") else 0
    start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"{market_code}.{symbol}",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "klt": "101",
        "fqt": "1",
        "beg": start,
        "end": end,
    }
    try:
        r = _eastmoney_get(url, params)
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        rows = []
        for line in klines:
            parts = line.split(",")
            rows.append({
                "日期": parts[0],
                "开盘": float(parts[1]), "收盘": float(parts[2]),
                "最高": float(parts[3]), "最低": float(parts[4]),
                "成交量": float(parts[5]), "成交额": float(parts[6]),
                "振幅": float(parts[7]) if parts[7] else 0,
                "涨跌幅": float(parts[8]) if parts[8] else 0,
                "涨跌额": float(parts[9]) if parts[9] else 0,
                "换手率": float(parts[10]) if parts[10] else 0,
            })
        df = pd.DataFrame(rows)
        df.sort_values("日期", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df.tail(TRADING_DAYS_NEEDED)
    except Exception as e:
        return None


# ====== 策略 ======
def check_strategy_1(df: pd.DataFrame) -> bool:
    if df is None or len(df) < 3:
        return False
    d1 = df.iloc[-2]
    d2 = df.iloc[-1]
    surge = d1["涨跌幅"]
    step = d2["涨跌幅"]
    if surge < SURGE_THRESHOLD:
        return False
    if not (0 < step < SURGE_THRESHOLD):
        return False
    vol_d1 = d1["成交量"]
    avg_vol = df["成交量"].iloc[-7:-2].mean()
    if avg_vol <= 0 or vol_d1 < avg_vol * VOLUME_RATIO:
        return False
    return True


def check_strategy_2(df: pd.DataFrame) -> bool:
    if df is None or len(df) < 25:
        return False
    df["ma20"] = df["收盘"].rolling(20).mean()
    close = df["收盘"].values
    ma20 = df["ma20"].values
    if not ma20[-1] > ma20[-5]:
        return False
    if not any(close[-6:-1] > ma20[-6:-1]):
        return False
    diff_pct = (close[-1] - ma20[-1]) / ma20[-1] * 100
    if abs(diff_pct) > MAX_PULLBACK_PCT:
        return False
    avg_vol_5 = df["成交量"].iloc[-6:-1].mean()
    vol_today = df["成交量"].iloc[-1]
    if avg_vol_5 > 0 and vol_today >= avg_vol_5:
        return False
    return True


def analyze_stock(code: str, name: str) -> tuple:
    """获取K线并检测策略，返回 (code, name, s1_result, s2_result)"""
    df = get_history(code)
    if df is None or len(df) < 20:
        return (code, name, None, None)

    r1 = None
    if check_strategy_1(df):
        d1 = df.iloc[-2]
        avg_v = max(df["成交量"].iloc[-7:-2].mean(), 1)
        r1 = {
            "代码": code, "名称": name,
            "前日涨幅": round(d1["涨跌幅"], 2),
            "今日涨幅": round(df.iloc[-1]["涨跌幅"], 2),
            "量比": round(d1["成交量"] / avg_v, 2),
            "收盘": df.iloc[-1]["收盘"],
        }

    r2 = None
    if check_strategy_2(df):
        ma20_val = round(df["ma20"].iloc[-1], 2)
        close_now = df["收盘"].iloc[-1]
        avg_v5 = max(df["成交量"].iloc[-6:-1].mean(), 1)
        r2 = {
            "代码": code, "名称": name,
            "现价": close_now,
            "ma20": ma20_val,
            "偏离%": round((close_now - ma20_val) / ma20_val * 100, 1),
            "缩量": round(df["成交量"].iloc[-1] / avg_v5, 2),
            "收盘": close_now,
        }

    return (code, name, r1, r2)


# ====== 通知 ======
def build_message(hits_s1: list, hits_s2: list) -> str:
    lines = [f"A股选股结果 {today_str}\n"]
    lines.append(f"【策略1 首日大涨+小碎步】共 {len(hits_s1)} 只\n")
    for s in hits_s1[:10]:
        lines.append(f"  {s['代码']} {s['名称']}  前日 {s['前日涨幅']:+.1f}%  今 {s['今日涨幅']:+.1f}%")
    lines.append(f"\n【策略2 回踩20日线】共 {len(hits_s2)} 只\n")
    for s in hits_s2[:10]:
        lines.append(f"  {s['代码']} {s['名称']}  MA20 {s['ma20']:.2f}  偏离 {s['偏离%']:+.1f}%")
    return "\n".join(lines)


def notify_file(hits_s1: list, hits_s2: list, output_dir: str = "."):
    lines = [f"=== A股选股结果  {today_str}  {now_ts} ===", ""]
    lines.append(f"【策略1】首日大涨+次日小碎步（共 {len(hits_s1)} 只）")
    lines.append("-" * 60)
    if hits_s1:
        for s in hits_s1:
            lines.append(f"  {s['代码']} {s['名称']}  前日 {s['前日涨幅']:+.1f}%  今日 {s['今日涨幅']:+.1f}%  量比 {s['量比']:.2f}")
    else:
        lines.append("  （无匹配）")
    lines.append("")
    lines.append(f"【策略2】回踩20日线的前期强势股（共 {len(hits_s2)} 只）")
    lines.append("-" * 60)
    if hits_s2:
        for s in hits_s2:
            lines.append(f"  {s['代码']} {s['名称']}  现价 {s['现价']:.2f}  MA20 {s['ma20']:.2f}  偏离 {s['偏离%']:+.1f}%  缩量 {s['缩量']:.2f}x")
    else:
        lines.append("  （无匹配）")
    out = os.path.join(output_dir, f"选股结果_{now_ts}.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"结果已写入 {out}")
    return out


def notify_wechat(hits_s1: list, hits_s2: list, webhook_url: str):
    import requests
    msg = build_message(hits_s1, hits_s2)
    try:
        r = requests.post(webhook_url, json={"msgtype": "text", "text": {"content": msg}}, timeout=10)
        if r.status_code == 200:
            log("企业微信通知发送成功")
        else:
            log(f"企业微信通知失败 {r.status_code}: {r.text}")
    except Exception as e:
        log(f"企业微信通知异常: {e}")


def notify_serverchan(hits_s1: list, hits_s2: list, sendkey: str):
    import requests
    title = f"A股选股 {today_str}  S1×{len(hits_s1)} S2×{len(hits_s2)}"
    content = build_message(hits_s1, hits_s2).replace("\n", "\n\n")
    try:
        r = requests.post(f"https://sct.ftqq.com/{sendkey}.send", data={"title": title, "desp": content}, timeout=10)
        data = r.json()
        if data.get("code") == 0:
            log("Server酱通知发送成功")
        else:
            log(f"Server酱通知失败: {data.get('message', r.text)}")
    except Exception as e:
        log(f"Server酱通知异常: {e}")


def notify_pushplus(hits_s1: list, hits_s2: list, token: str):
    import requests
    title = f"A股选股 {today_str}  S1×{len(hits_s1)} S2×{len(hits_s2)}"
    content = build_message(hits_s1, hits_s2)
    try:
        r = requests.post("https://www.pushplus.plus/send", json={"token": token, "title": title, "content": content}, timeout=10)
        data = r.json()
        if data.get("code") == 200:
            log("PushPlus通知发送成功")
        else:
            log(f"PushPlus通知失败: {data.get('msg', r.text)}")
    except Exception as e:
        log(f"PushPlus通知异常: {e}")


# ====== 主流程 ======
def main():
    parser = argparse.ArgumentParser(
        description="A股选股助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""推送方式示例:
  python stock_screener.py --serverchan SCTxxxxx
  python stock_screener.py --pushplus xxxxx
  python stock_screener.py --wechat-url https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
        """,
    )
    parser.add_argument("--intraday", action="store_true", help="盘中模式")
    parser.add_argument("--wechat-url", type=str, help="企业微信机器人 Webhook URL")
    parser.add_argument("--serverchan", type=str, metavar="SENDKEY", help="Server酱 SendKey")
    parser.add_argument("--pushplus", type=str, metavar="TOKEN", help="PushPlus Token")
    parser.add_argument("--output-dir", type=str, default=".", help="结果输出目录")
    parser.add_argument("--max-stocks", type=int, default=0, help="最多分析 N 只（按交易所列表顺序，默认全部）")
    parser.add_argument("--workers", type=int, default=10, help="并发数（默认 10）")
    parser.add_argument("--no-progress", action="store_true", help="不输出逐条进度")
    args = parser.parse_args()

    all_stocks = get_stock_list(args.max_stocks)
    if all_stocks.empty:
        log("获取股票列表失败，退出")
        sys.exit(1)

    pool_size = min(args.workers, len(all_stocks))
    log(f"并发 {pool_size} 个线程分析 {len(all_stocks)} 只股票 ...")
    hits_s1, hits_s2 = [], []
    done = 0
    total = len(all_stocks)
    last_report = time.time()

    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        fut_map = {}
        for _, row in all_stocks.iterrows():
            code = str(row["代码"]).strip()
            name = str(row["名称"]).strip()
            fut = pool.submit(analyze_stock, code, name)
            fut_map[fut] = (code, name)

        for fut in as_completed(fut_map):
            code, name, r1, r2 = fut.result()
            done += 1
            if r1:
                hits_s1.append(r1)
            if r2:
                hits_s2.append(r2)
            now = time.time()
            if args.no_progress:
                if done == total or (done % (total // 10 or 1)) == 0:
                    log(f"  进度 {done}/{total}")
            else:
                if done % 100 == 0 or now - last_report > 5:
                    log(f"  进度 {done}/{total}  命中 S1={len(hits_s1)}  S2={len(hits_s2)}  当前 {code} {name}")
                    last_report = now

    hits_s1.sort(key=lambda x: x["量比"], reverse=True)
    hits_s2.sort(key=lambda x: abs(x["偏离%"]))

    log("=" * 50)
    log(f"策略1（首日大涨+小碎步）: {len(hits_s1)} 只")
    for s in hits_s1[:10]:
        log(f"  {s['代码']} {s['名称']}  前日 {s['前日涨幅']:+.1f}%  今 {s['今日涨幅']:+.1f}%")
    log(f"策略2（回踩20日线）: {len(hits_s2)} 只")
    for s in hits_s2[:10]:
        log(f"  {s['代码']} {s['名称']}  MA20 {s['ma20']:.2f}  偏离 {s['偏离%']:+.1f}%")

    notify_file(hits_s1, hits_s2, args.output_dir)

    if args.wechat_url:
        notify_wechat(hits_s1, hits_s2, args.wechat_url)
    if args.serverchan:
        notify_serverchan(hits_s1, hits_s2, args.serverchan)
    if args.pushplus:
        notify_pushplus(hits_s1, hits_s2, args.pushplus)

    log("Done.")


if __name__ == "__main__":
    main()
