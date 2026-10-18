import time
import threading
import RPi.GPIO as GPIO

from alarm import alarm
from alarm.notifier import send_text_message

BUTTON_PIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def monitor():
    while True:
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            print("[SOS] Button pressed")

            alarm.trigger(10)

            send_text_message(
                "🚨 SOS button pressed!\nImmediate assistance is required."
            )

            # Wait until button released
            while GPIO.input(BUTTON_PIN) == GPIO.LOW:
                time.sleep(0.05)

            # Debounce
            time.sleep(0.5)

        time.sleep(0.05)


def start():
    threading.Thread(target=monitor, daemon=True).start()
