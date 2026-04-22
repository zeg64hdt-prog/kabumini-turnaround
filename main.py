import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=+9), 'JST')

# (analyze_fundamentals, judge_turnaround, send_line は上記と同様)
# ※ CSVの読み込み先とタイトルの表示のみ株ミニ用に最適化しています。

def analyze_fundamentals(t_obj):
    score = 0
    try:
        info = t_obj.info
        if info.get('operatingMargins', 0) >= 0.10: score += 1
        per = info.get('trailingPE', 0)
        if per and 10 <= per <= 15: score += 1
        if info.get('returnOnEquity', 0) >= 0.08: score += 1
        if info.get('dividendYield', 0) >= 0.03: score += 1
        return "★" * score if score > 0 else ""
    except: return ""

def judge_turnaround(ticker_code, name):
    try:
        t_obj = yf.Ticker(f"{ticker_code}.T")
        data = t_obj.history(period="1y", interval="1d") 
        if data.empty or len(data) < 75: return None
        close, vol = data['Close'], data['Volume']
        p_now, p_pre = float(close.iloc[-1]), float(close.iloc[-2])
        avg_vol_5 = vol.tail(5).mean()
        if avg_vol_5 < 50000 and (p_now * avg_vol_5) < 50000000: return None
        avg_vol_25 = vol.tail(25).mean()
        recent_vol_3 = vol.tail(3).mean()
        if recent_vol_3 > avg_vol_25 * 0.8: return None
        star = analyze_fundamentals(t_obj)
        if len(star) < 2: return None
        ma75 = close.rolling(75).mean()
        m75_now, m75_pre = ma75.iloc[-1], ma75.iloc[-2]
        if p_now > m75_now:
            if p_pre <= m75_pre or (p_now > m75_now and recent_vol_3 < avg_vol_25 * 0.7):
                return f"🌟【充填】{star}{ticker_code} {name}({p_now:.0f}円)"
        return None
    except: return None

def send_line(message):
    token, uid = os.environ.get('LINE_ACCESS_TOKEN'), os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for i in range(0, len(message), 4500):
        payload = {"to": uid, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        requests.post(url, headers=headers, json=payload, timeout=20)
        time.sleep(1)

def main():
    if not os.path.exists("kabumini.csv"): # 株ミニ用のCSVを参照
        print("kabumini.csvが見つかりません"); return
    df = pd.read_csv("kabumini.csv", encoding='utf-8-sig')
    c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
    n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
    stocks = df[[c_col, n_col]].dropna().values.tolist()
    res = []
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if c.isdigit():
            out = judge_turnaround(c, str(name))
            if out: res.append(out)
        if (i+1)%15 == 0: time.sleep(0.05)
    now_jst = datetime.now(JST)
    msg = f"🔄 夕方：株ミニ転換判定({now_jst.strftime('%m/%d %H:%M')})\n"
    msg += "条件: ★★以上 / 75日線突破 / 出来高静止中\n\n"
    msg += "\n".join(res) if res else "該当なし"
    send_line(msg)

if __name__ == "__main__": main()
