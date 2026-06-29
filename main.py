import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=+9), 'JST')

def analyze_fundamentals(t_obj):
    """【ミーム株排除】売上成長を最重視しつつ、赤字・低収益の仕手投機株を弾く"""
    score = 0
    try:
        info = t_obj.info
        
        # --- ①【ミーム株排除】最終損益が黒字であること（赤字は即除外） ---
        net_income = info.get('netIncomeToCommon')
        if net_income is None or net_income <= 0: return None
        
        # --- ②【ミーム株排除】本業が低収益でないこと（営業利益率 5%未満は即除外） ---
        op_margin = info.get('operatingMargins')
        if op_margin is None or op_margin < 0.05: return None
        if op_margin >= 0.10: score += 1 
        
        # --- ③【最重要】売上高成長率フィルター (前年同期比 5%以上が必須) ---
        rev_growth = info.get('revenueGrowth')
        if rev_growth is None or rev_growth < 0.05: return None
        score += 1
        
        # --- ④ PER 30倍以下 ---
        per = info.get('trailingPE', 0)
        if per and per <= 30: score += 1
        
        # --- ⑤ ROE 8%以上 ---
        if info.get('returnOnEquity', 0) >= 0.08: score += 1
        
        return "★" * score
    except:
        return None

def judge_turnaround(ticker_code, name):
    try:
        t_obj = yf.Ticker(f"{ticker_code}.T")
        data = t_obj.history(period='2y', interval='1d') 
        if data.empty or len(data) < 200: return None
        
        close, vol = data['Close'], data['Volume']
        p_now = float(close.iloc[-1])
        
        # --- ① 流動性フィルター ---
        avg_vol_5 = vol.tail(5).mean()
        if avg_vol_5 < 50000 and (p_now * avg_vol_5) < 50000000: return None

        # --- ② 新・財務チェック (増収かつ黒字・利益率クリアが絶対条件) ---
        star = analyze_fundamentals(t_obj)
        if not star: return None 

        # --- ③ 各種移動平均の計算 ---
        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        ma200 = close.rolling(200).mean()
        
        m5_n, m25_n, m75_n = ma5.iloc[-1], ma25.iloc[-1], ma75.iloc[-1]
        m200_n, m200_p20 = ma200.iloc[-1], ma200.iloc[-21]

        # --- ④ 上昇トレンド（パーフェクトオーダー） ---
        if not (m5_n > m25_n > m75_n and p_now > m75_n): return None

        # --- ⑤ チャートの「よこよこ」（直近5日間の値幅収縮が3%以内） ---
        recent_5_days = close.tail(5)
        if (recent_5_days.max() - recent_5_days.min()) / recent_5_days.min() > 0.03: return None

        # --- ⑥ 出来高の「静けさ」（25日平均の70%以下） ---
        if vol.tail(3).mean() > vol.tail(25).mean() * 0.7: return None

        # --- ⑦ 長期200日線による加点判定 ---
        is_200_safe = (m200_n > m200_p20) and (p_now > m200_n)
        label = "🚀🌟🌟【高成長・極よこよこ】" if is_200_safe else "🚀🌟【高成長・よこよこ】"
        
        return f"{label}{star}{ticker_code} {name}({p_now:.0f}円)"
    except: 
        return None

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
        msg = f"🔄 夕方：株ミニ増収×中段よこよこ判定({now_jst.strftime('%m/%d %H:%M')})\n"
        msg += "条件: 黒字＆増収5%必須 / 上昇トレンド保ち合い / 出来高極小\n\n"
        msg += "\n".join(res)
        send_line(msg)

if __name__ == "__main__": 
    main()
