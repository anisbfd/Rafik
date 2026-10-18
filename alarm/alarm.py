import threading
import time
import RPi.GPIO as GPIO

LED_PIN = 17
BUZZER_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

GPIO.output(LED_PIN, GPIO.LOW)
GPIO.output(BUZZER_PIN, GPIO.LOW)

def trigger(seconds=10):
    def _alarm():
        end_time = time.time() + seconds

        while time.time() < end_time:
            # ON
            GPIO.output(LED_PIN, GPIO.HIGH)
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            time.sleep(0.25)

            # OFF
            GPIO.output(LED_PIN, GPIO.LOW)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            time.sleep(0.25)

    threading.Thread(target=_alarm, daemon=True).start()