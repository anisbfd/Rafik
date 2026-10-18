import requests

BOT_TOKEN = "8780823958:AAGuIc-Y9pU-rX0YWNTTqpbes9EdoQeuhRA"
CHAT_ID = "6429866535"


def send_text_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=10
    )
