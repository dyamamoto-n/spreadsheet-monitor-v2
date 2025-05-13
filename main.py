import time
import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# 環境変数から設定
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Google Sheets 認証（環境変数からJSONを読み込む形式）
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_info = json.loads(os.environ["GCP_CREDENTIALS"])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
client = gspread.authorize(credentials)

# 通知抑制設定（6時間）
RE_NOTIFY_INTERVAL_HOURS = 6

# Slack通知（Bot名・アイコン固定：Spyke Alert ⚠️）
def send_slack(message):
    payload = {
        "text": message,
        "username": "Spyke Alert",
        "icon_emoji": ":warning:"
    }
    requests.post(SLACK_WEBHOOK_URL, json=payload)

# 通知履歴を読み込む
def load_notified_from_sheet():
    try:
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet("通知履歴")
        records = sheet.get_all_records()
        notified = {}
        for record in records:
            key = f"{record['シート名']}_{record['ID']}"
            notified[key] = record['通知日時']
        return notified
    except Exception as e:
        print("通知履歴の読み込みに失敗しました:", e)
        return {}

# 通知履歴に追記のみ行う（append_row）
def save_notified_to_sheet(sheet_name, id_, timestamp):
    try:
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet("通知履歴")
        sheet.append_row([id_, sheet_name, timestamp])
        print(f"[通知履歴] 書き込み成功: {id_} ({sheet_name}) → {timestamp}")
    except Exception as e:
        print("通知履歴の書き込みに失敗しました:", e)

# シートごとの監視処理（Bot名・アイコンは使わない）
def check_sheet(sheet_name, threshold, message_template):
    notified = load_notified_from_sheet()
    now = datetime.datetime.now()

    try:
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(sheet_name)
    except Exception as e:
        print(f"\u274c シート '{sheet_name}' を開けませんでした: {e}")
        return

    print(f"\u2705 シート '{sheet_name}' を開いて処理開始")

    try:
        rows = sheet.get("B2:D10")  # B列=値, C列=見出し, A列はIDと仮定（この後取得する）
        ids = sheet.get("A2:A10")   # A列=ID（別取得）
    except Exception as e:
        print(f"\u26a0\ufe0f セル範囲の取得に失敗しました: {e}")
        return

    for i in range(len(rows)):
        try:
            id_ = ids[i][0]  # A列
            value = int(rows[i][0])  # B列（値）
            headline = rows[i][1]    # C列（見出し）
        except (IndexError, ValueError):
            continue

        print(f"[{sheet_name}] 処理中のID: {id_}, 値: {value}, 見出し: {headline}")

        unique_key = f"{sheet_name}_{id_}"
        last_time_str = notified.get(unique_key)
        if last_time_str:
            last_time = datetime.datetime.fromisoformat(last_time_str)
            if (now - last_time).total_seconds() < RE_NOTIFY_INTERVAL_HOURS * 3600:
                print(f"[{sheet_name}] {id_} は6時間以内に通知済み、スキップ")
                continue

        if value > threshold:
            message = message_template.format(headline=headline)
            send_slack(message)
            print(f"[{sheet_name}] \u2728 通知送信：{headline}（{value}）")
            save_notified_to_sheet(sheet_name, id_, now.isoformat())

# === 各シートごとの設定 ===

check_sheet(
    sheet_name="LINE",
    threshold=400,
    message_template="`{headline}`\nこちらの記事がLINEで読まれています！確認して必要なら関連リンクを変更してください。"
)

check_sheet(
    sheet_name="Smartnews",
    threshold=300,
    message_template="`{headline}`\nこちらの記事がSmartnewsで読まれています！確認して必要なら関連リンクを変更してください。"
)

# シート一覧をログに表示（デバッグ用）
sheets = client.open_by_key(SPREADSHEET_KEY).worksheets()
print("\n\u2139️ 存在するシート一覧:")
for s in sheets:
    print("-", s.title)
