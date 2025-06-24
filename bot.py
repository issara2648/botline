from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage as V3TextMessage
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import gspread
import threading
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# LINE credentials
LINE_CHANNEL_ACCESS_TOKEN = 'y+vPQXG2y6hHJ5mfpkNDAC9cXi+8lRwa4+6pnC6o/zO51IUFJiJ2EDd2eU9uZlLyvqJemmZt0ugML7yJR4GWDWw3CLe2zME8Uw01i/ONXnYuXqOge6I0KjpxAv4mE6DEgUk2dS8xRHuWOjSo75goAwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '24826367b5fd601d2b34f7adbe6ec59b'

# LINE Messaging API setup (v3)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
Configuration.set_default(configuration)
api_client = ApiClient(configuration=configuration)
messaging_api = MessagingApi(api_client)

# LINE Webhook Handler
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Sheet setup
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('civil-victory-461817-h9-8e1dd064f172.json', scope)
client = gspread.authorize(creds)
sheet = client.open('products').sheet1

# LINE webhook
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent)
def handle_message(event):
    if not isinstance(event.message, TextMessageContent):
        return

    user_id = event.source.user_id
    user_text = event.message.text.strip()

    # 1. ตอบกลับทันที ด้วย with ApiClient
    try:
        with ApiClient(configuration=configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[V3TextMessage(text="รับออเดอร์แล้วค่ะ กำลังประมวลผล..")]
                )
            )
    except Exception as e:
        print("Reply error:", e)

    # 2. ทำงาน background ส่ง push message
    threading.Thread(target=process_order, args=(user_id, user_text)).start()

def process_order(user_id, user_text):
    try:
        codes = user_text.split()
        records = sheet.get_all_records()
        reply_lines = []
        total = 0

        for code in codes:
            item = next((row for row in records if str(row['รหัสสินค้า']) == code), None)
            if item:
                name = item['ชื่อสินค้า']
                price = int(item['ราคา'])
                reply_lines.append(f"{code}. {name} - {price} บาท")
                total += price
            else:
                reply_lines.append(f"{code}. ❌ ไม่พบสินค้า")

        reply_lines.append(f"\nรวมทั้งหมด: {total} บาท")
        final_reply = "\n".join(reply_lines)

        # ส่ง push message ด้วย with ApiClient
        with ApiClient(configuration=configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[V3TextMessage(text=final_reply)]
                )
            )

    except Exception as e:
        print("Push message error:", e)
        with ApiClient(configuration=configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[V3TextMessage(text="เกิดข้อผิดพลาดในการค้นหาสินค้า")]
                )
            )


if __name__ == "__main__":
    app.run(port=5000)
