"""
Bybit P2P Monitor
-----------------
環境変数で各種設定を行います。

必須:
  TG_TOKEN            Telegram Bot Token (BotFatherで取得)
  TG_CHAT_ID          送信先チャットID (数値または @channelusername)
オプション:
  BYBIT_KEY           Bybit API Key (Read‑only) – 公開広告の取得だけなら無くてもOK
  BYBIT_SECRET        Bybit API Secret
  REVOLUT_PM_IDS      Revolut決済のpayment IDをカンマ区切りで指定 (デフォルト: 377)
  INTERVAL_SEC        ポーリング間隔(秒) デフォルト: 30
"""

import os
import time
import logging
from typing import List, Dict, Set

import requests
from bybit_p2p import P2P
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")



TG_TOKEN  = os.environ['TG_TOKEN']  
TG_CHAT_ID = os.environ['TG_CHAT_ID']
BYBIT_KEY = os.getenv('BYBIT_KEY')
BYBIT_SECRET = os.getenv('BYBIT_SECRET')
REVOLUT_PM_IDS = set(os.getenv('REVOLUT_PM_IDS', '377').split(','))
INTERVAL = int(os.getenv('INTERVAL_SEC', '30'))

bot = Bot(TG_TOKEN)

api = P2P(testnet=False,
          api_key=BYBIT_KEY,
          api_secret=BYBIT_SECRET) if BYBIT_KEY and BYBIT_SECRET else P2P(testnet=False)



logging.basicConfig(
    level=logging.DEBUG,             # ← DEBUG に
    format="%(asctime)s %(levelname)s %(message)s"
)

# 監視ルール
rules: List[Dict] = [
    # 日本円 – 任意の決済方法
    dict(currency="JPY", side="0", max_price=140),      # BUY
    dict(currency="JPY", side="1", min_price=165),      # SELL
    # EUR – Revolut
    dict(currency="EUR", side="0", max_price=0.863, pm_required=True),
    dict(currency="EUR", side="1", min_price=1.0, pm_required=True),
    # USD – Revolut (BUYのみ)
    dict(currency="USD", side="0", max_price=0.9, pm_required=True),
    # GBP – Revolut
    dict(currency="GBP", side="0", max_price=0.75, pm_required=True),
    dict(currency="GBP", side="1", min_price=0.888, pm_required=True),
]

# 通知済み広告IDを保持（メモリ上。永続化する場合はRedis等を使用）
notified_ids: Set[str] = set()


def main():
    logging.info("Started monitor…")
    logging.debug("=== monitor loop START ===")   # 追加行も 4 スペース揃え

    while True:
        for rule in rules:
            check_rule(rule)
        time.sleep(INTERVAL)

def check_rule(rule: Dict):
    currency, side = rule['currency'], rule['side']
    logging.debug(f"[RULE] {rule}")  # ① どのルールを処理中か

    try:
        res = api.get_online_ads(tokenId="USDT", currencyId=currency, side=side)
        items = res['result']['items']
    except Exception as e:
        logging.error(f"[API ERROR] {e}")
        return

    logging.debug(f"[API] {currency}/{side} → {len(items)} items")

    for ad in items:
        ad_id = ad['id']
        price = float(ad['price'])
        payments = set(ad.get('payments', []))
        logging.debug(f"[AD] id={ad_id}, price={price}, payments={payments}")  # ② 各広告

        if ad_id in notified_ids:
            logging.debug(f"[SKIP] already notified {ad_id}")
            continue

        ok = False
        if 'max_price' in rule and price <= rule['max_price']:
            ok = True
        if 'min_price' in rule and price >= rule['min_price']:
            ok = True

        if ok:
            logging.debug(f"[MATCH] {ad_id} matches rule")  # ③ マッチした
            try:
                bot.send_message(chat_id=TG_CHAT_ID, text="テスト通知")  # 実際の通知
                logging.debug(f"[SENT] notification for {ad_id}")
                notified_ids.add(ad_id)
            except Exception as e:
                logging.error(f"[TG ERROR] {e}")

if __name__ == "__main__":
    main()   # 無限ループのまま起動し続ける



