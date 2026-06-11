import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=+9), 'JST')

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
        data = t_obj.history(period='1y', interval='1d') 
        if data.empty or len(data) < 75: return None
        
        close, vol = data['Close'], data['Volume']
        p_now = float(close.iloc[-1])
        
        avg_vol_5 = vol.tail(5).mean()
        if avg_vol_5 < 50000 and (p_now * avg_vol_5) < 50000000: return None

        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        ma200 = close.rolling(200).mean()
        
        m5_n, m25_n, m75_n = ma5.iloc[-1], ma25.iloc[-1], ma75.iloc[-1]
        m200_n, m200_p20 = ma200.iloc[-1], ma200.iloc[-21]

        star = analyze_fundamentals(t_obj)
        if len(star) < 2: return None

        # 上昇パーフェクトオーダー
        if not (m5_n > m25_n > m75_n and p_now > m75_n): return None

        # 5日間の値幅が3%以内（よこよこ）
        recent_5_days = close.tail(5)
        if (recent_5_days.max() - recent_5_days.min()) / recent_5_days.min() > 0.03: return None

        # 出来高が25日平均の70%以下（エネルギー充填）
        if vol.tail(3).mean() > vol.tail(25).mean() * 0.7: return None

        is_200_safe = (m200_n > m200_p20) and (p_now > m200_n)
        label = "🚀🌟🌟【極・よこよこ】" if is_200_safe else "🚀🌟【真・よこよこ】"
        
        return f"{label}{star}{ticker_code} {name}({p_now:.0f}円)"
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
    if not os.path.exists("kabumini.csv"): return
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
    
    if res:
        now_jst = datetime.now(JST)
        msg = f"🔄 夕方：株ミニ中段よこよこ判定({now_jst.strftime('%m/%d %H:%M')})\n"
        msg += "条件: 上昇中パーフェクトオーダー / 5日値幅3%以内 / 出来高激減\n\n"
        msg += "\n".join(res)
        send_line(msg)

if __name__ == "__main__": main()
