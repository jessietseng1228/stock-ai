import requests

CHANNEL_ACCESS_TOKEN = "kGWl+cSBUwKrKWFmvyDCp0kPabfuiCK5Rtcc2SXPX93jJvTA6e0+X5TkySmutdCrJfCBMEP4UFnguW1SObeNdgVTCXEzGurdKUaCwjNxZHOydseQwQh9Md3EJ1OCM/QRWsN6Va56KMP32J8valpqZwdB04t89/1O/w1cDnyilFU="

USER_ID = "自己LINE ID（等下教你拿）"

url = "https://api.line.me/v2/bot/message/push"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
}

message = {
    "to": USER_ID,
    "messages": [
        {
            "type": "text",
            "text": "📈 股票系統測試成功！Python 已經可以發 LINE 訊息了"
        }
    ]
}

res = requests.post(url, headers=headers, json=message)

print(res.status_code)
print(res.text)