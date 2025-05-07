"""
Bybit P2P Monitor
-----------------
環境変数で各種設定を行います。

必須:
  TG_TOKEN            Telegram Bot Token (BotFatherで取得)
  TG_CHAT_ID          送信先チャットID (数値または @channelusername)
オプション:
  BYBIT_KEY           Bybit API Key (Read-only) – 公開広告の取得だけなら無くてもOK
  BYBIT_SECRET        Bybit API Secret
  REVOLUT_PM_IDS      Revolut決済のpayment IDをカンマ区切りで指定 (デフォルト: 377)
  INTERVAL_SEC        ポーリング間隔(秒) デフォルト: 120
"""

import os
import time
import logging
import requests
from typing import List, Dict, Set
from bybit_p2p import P2P

# ログ設定（DEBUGレベルで全てのログを出力）
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

# 環境変数読み込み
TG_TOKEN       = os.environ['TG_TOKEN']
TG_CHAT_ID     = os.environ['TG_CHAT_ID']
BYBIT_KEY      = os.getenv('BYBIT_KEY')
BYBIT_SECRET   = os.getenv('BYBIT_SECRET')
REVOLUT_PM_IDS = set(os.getenv('REVOLUT_PM_IDS', '377').split(','))
INTERVAL       = int(os.getenv('INTERVAL_SEC', '30'))

# Telegram Bot API を直接叩く関数
def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logging.debug(f"[SENT] {text!r}")
    except Exception as e:
        logging.error(f"[TG ERROR] {e}")

# Bybit P2P API 初期化
if BYBIT_KEY and BYBIT_SECRET:
    api = P2P(testnet=False, api_key=BYBIT_KEY, api_secret=BYBIT_SECRET)
else:
    api = P2P(testnet=False)

# 監視ルール定義
rules: List[Dict] = [
    dict(currency="JPY", side="0", max_price=140),   # JPY: 買い ≤140
    dict(currency="JPY", side="1", min_price=165),   # JPY: 売り ≥165
    dict(currency="EUR", side="0", max_price=0.82), # EUR: 買い ≤0.863
    dict(currency="EUR", side="1", min_price=1.00),   # EUR: 売り ≥1.0
    dict(currency="USD", side="0", max_price=0.9),   # USD: 買い ≤0.9
    #dict(currency="USD", side="1", min_price=1.2),   # USD: 売り ≥1.2
    dict(currency="GBP", side="0", max_price=0.75),  # GBP: 買い ≤0.75
    dict(currency="GBP", side="1", min_price=0.888), # GBP: 売り ≥0.888
]

# 通知済み広告IDを保持（メモリ上）
notified_ids: Set[str] = set()

def check_rule(rule: Dict):
    currency, side = rule['currency'], rule['side']
    logging.debug(f"[RULE] {rule}")

    try:
        res = api.get_online_ads(
            tokenId="USDT",
            currencyId=currency,
            side=side,
        )
        items = res['result']['items']
    except Exception as e:
        logging.error(f"[API ERROR] {e}")
        return

    logging.debug(f"[API] {currency}/{side} → {len(items)} items")

    for ad in items:
        ad_id = ad['id']
        price = float(ad['price'])
        payments = set(ad.get('payments', []))
        logging.debug(f"[AD] id={ad_id}, price={price}, payments={payments}")

        if ad_id in notified_ids:
            logging.debug(f"[SKIP] already notified {ad_id}")
            continue

        if rule.get('pm_required') and payments.isdisjoint(REVOLUT_PM_IDS):
            logging.debug(f"[SKIP] Revolut required but missing for {ad_id}")
            continue

        ok = False
        if 'max_price' in rule and price <= rule['max_price']:
            ok = True
        if 'min_price' in rule and price >= rule['min_price']:
            ok = True

        if ok:
            logging.debug(f"[MATCH] {ad_id} matches rule")
            message = (
                f"🔥 P2Pレート検知!\n"
                f"{'買い' if side=='0' else '売り'} {currency} ⇄ USDT\n"
                f"価格: {price} {currency}/USDT\n"
                f"広告主: {ad['nickName']} (ID {ad_id})\n"
                f"決済方法IDs: {', '.join(payments)}\n"
                f"https://www.bybit.com/fiat/trade/otc/{'buy' if side=='0' else 'sell'}/USDT/{currency}"
            )
            send_telegram(message)
            notified_ids.add(ad_id)
            logging.info("通知済み %s", ad_id)

def main():
    # 起動時テスト通知
    send_telegram("🚀 モニタースタート通知（本番環境テスト）")
    logging.debug("[STARTUP TEST] sent startup notification")

    logging.info("Started monitor…")
    logging.debug("=== monitor loop START ===")
    while True:
        for rule in rules:
            check_rule(rule)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
