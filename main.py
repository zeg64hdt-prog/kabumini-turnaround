import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本標準時 (JST) の設定
JST = timezone(timedelta(hours=+9), 'JST')

def analyze_fundamentals(t_obj):
    """財務5項目をチェックし、適合数をカウント（★印）"""
    score = 0
    try:
        info = t_obj.info
        # 1. 営業利益率 10%以上
        if info.get('operatingMargins', 0) >= 0.10: score += 1
        # 2. PER 10倍〜15倍（割安かつ期待あり）
        per = info.get('trailingPE', 0)
        if per and 10 <= per <= 15: score += 1
        # 3. ROE 8%以上
        if info.get('returnOnEquity', 0) >= 0.08: score += 1
        # 4. 配当利回り 3%以上
        if info.get('dividendYield', 0) >= 0.03: score += 1
        
        return "★" * score if score > 0 else ""
    except:
        return ""

def judge_turnaround(ticker_code, name):
    """
    加点方式・転換判定ロジック
    基本：75日線上昇 ＋ 5日線接近 ＋ 出来高静止（🌟）
    加点：200日線上昇 ＋ 200日線より上に株価位置（🌟🌟）
    """
    try:
        t_obj = yf.Ticker(f"{ticker_code}.T")
        # 200日線の計算と、土日祝を考慮して2年分のデータを取得
        data = t_obj.history(period='2y', interval='1d') 
        if data.empty or len(data) < 200: return None
        
        close, vol = data['Close'], data['Volume']
        p_now = float(close.iloc[-1])
        
        # --- ① 流動性フィルター ---
        avg_vol_5 = vol.tail(5).mean()
        if avg_vol_5 < 50000 and (p_now * avg_vol_5) < 50000000:
            return None

        # --- ② 移動平均線の計算 ---
        ma5 = close.rolling(5).mean()
        ma75 = close.rolling(75).mean()
        ma200 = close.rolling(200).mean()
        
        m5_now = ma5.iloc[-1]
        m75_now, m75_pre5 = ma75.iloc[-1], ma75.iloc[-6]
        m200_now, m200_pre20 = ma200.iloc[-1], ma200.iloc[-21] # 200日線は1ヶ月スパンで傾きを見る

        # --- ③ 財務チェック (★★以上を必須とする) ---
        star = analyze_fundamentals(t_obj)
        if len(star) < 2: return None

        # --- ④ 必須条件：75日線トレンド＆低乖離 ---
        # 75日線が5日前より高く、5日線との乖離が3%以内
        is_75_up = m75_now > m75_pre5
        is_close = abs(m5_now - m75_now) / m75_now <= 0.03
        
        if not (is_75_up and is_close): return None

        # --- ⑤ 必須条件：出来高の「静けさ」 ---
        # 直近3日の平均出来高が、過去25日平均の80%以下（エネルギー充填中）
        avg_vol_25 = vol.tail(25).mean()
        recent_vol_3 = vol.tail(3).mean()
        if recent_vol_3 > avg_vol_25 * 0.8: return None

        # --- ⑥ 加点判定：長期200日線の状態 ---
        # 200日線が上向き、かつ現在の株価が200日線より上にあるか
        is_200_safe = (m200_now > m200_pre20) and (p_now > m200_now)
        
        # 出力ラベルの決定
        label = "🌟🌟【極・充填】" if is_200_safe else "🌟【真・充填】"
        
        # 最終確認：株価が75日線の上にあること
        if p_now > m75_now:
            return f"{label}{star}{ticker_code} {name}({p_now:.0f}円)"
        
        return None
    except:
        return None

def send_line(message):
    """LINE Messaging API を使用して通知を送信"""
    token = os.environ.get('LINE_ACCESS_TOKEN')
    uid = os.environ.get('LINE_USER_ID')
    if not token or not uid: return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 4500文字を超える場合は分割送信
    for i in range(0, len(message), 4500):
        payload = {
            "to": uid,
            "messages": [{"type": "text", "text": message[i:i+4500]}]
        }
        try:
            requests.post(url, headers=headers, json=payload, timeout=20)
            time.sleep(1) # 連続送信による負荷軽減
        except:
            pass

def main():
    """メイン処理：CSVを読み込み全銘柄をスキャン"""
    if not os.path.exists("kabumini.csv"):
        print("kabumini.csv が見つかりません。")
        return

    # CSVの読み込み（コードと銘柄名の列を特定）
    df = pd.read_csv("kabumini.csv", encoding='utf-8-sig')
    c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
    n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
    stocks = df[[c_col, n_col]].dropna().values.tolist()

    res = []
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if c.isdigit():
            out = judge_turnaround(c, str(name))
            if out:
                res.append(out)
        
        # Yahoo Finance APIへの負荷を考慮し、15銘柄ごとに少し待機
        if (i+1) % 15 == 0:
            time.sleep(0.05)

    # 該当銘柄がある場合のみ通知
    if res:
        now_jst = datetime.now(JST)
        msg = f"🔄 夕方：株ミニ転換判定({now_jst.strftime('%m/%d %H:%M')})\n"
        msg += "🌟🌟=長期トレンドも万全 / 🌟=中期期待株\n\n"
        msg += "\n".join(res)
        send_line(msg)
    else:
        print("本日は条件に合致する銘柄はありませんでした。")

if __name__ == "__main__":
    main()
