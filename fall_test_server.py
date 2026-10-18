from flask import Flask, request
import cv2
import numpy as np
import threading
import time
import requests
from werkzeug.serving import WSGIRequestHandler
from alarm import alarm
import sos

sos.start()


WSGIRequestHandler.address_string = lambda self: self.client_address[0]

app = Flask(__name__)

# --- MobileNet-SSD person detector (same model used in the integrated fall_detector.py) ---
# expects deploy.prototxt + mobilenet_iter_73000.caffemodel in ~/health_companion/mobilenet_ssd/
PROTOTXT_PATH = "mobilenet_ssd/deploy.prototxt"
MODEL_PATH = "mobilenet_ssd/mobilenet_iter_73000.caffemodel"
net = cv2.dnn.readNetFromCaffe(PROTOTXT_PATH, MODEL_PATH)

PERSON_CLASS_ID = 15  # VOC class index for "person" in this model
CONF_THRESH = 0.4

# FALL_ASPECT_RATIO lowered from 1.0 -> 0.8 based on real test footage:
# - 03.mp4 (walking, no fall): max aspect_ratio seen = 0.61
# - 25.mp4 (real fall): aspect_ratio hit 2.02 lying down
# - test00.mp4 (real fall): aspect_ratio only reached 0.93 before the person
#   was lost from view -- with the old 1.0 threshold this fall was never flagged
# 0.8 catches both real falls with a solid margin above the walking baseline.
FALL_ASPECT_RATIO = 0.8

# --- Telegram notifier settings ---
TELEGRAM_BOT_TOKEN = "8780823958:AAGuIc-Y9pU-rX0YWNTTqpbes9EdoQeuhRA"
TELEGRAM_CHAT_ID = "6429866535"
TELEGRAM_ENABLED = True
ALERT_COOLDOWN_SEC = 15  # don't re-alert more often than this while a fall persists

_last_alert_time = 0
_alert_lock = threading.Lock()


def send_telegram_alert(frame, caption):
    """Debug version to test the background thread."""

    if not TELEGRAM_ENABLED:
        print("[telegram] disabled")
        return

    def _send():
        print("[telegram] thread started")

        try:
            ok, jpeg = cv2.imencode(".jpg", frame)

            if not ok:
                print("[telegram] failed to encode frame")
                return

            print("[telegram] image encoded")

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

            files = {
                "photo": ("fall.jpg", jpeg.tobytes(), "image/jpeg")
            }

            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption
            }

            print("[telegram] sending request...")

            response = requests.post(
                url,
                data=data,
                files=files,
                timeout=10
            )

            print("[telegram] status code:", response.status_code)
            print("[telegram] response:", response.text)

        except Exception as e:
            print("[telegram] exception:", e)

        print("[telegram] thread finished")

    print("[telegram] creating thread")

    t = threading.Thread(target=_send)
    t.daemon = True
    t.start()

    print("[telegram] thread launched")


def maybe_alert(frame, aspect_ratio):
    """Gate alerts behind a cooldown so a sustained fall doesn't spam Telegram."""
    global _last_alert_time
    with _alert_lock:
        now = time.time()
        if now - _last_alert_time < ALERT_COOLDOWN_SEC:
            return False
        _last_alert_time = now

    caption = f"Possible fall detected (aspect_ratio={aspect_ratio:.2f})"
    alarm.trigger(10)
    send_telegram_alert(frame, caption)
    return True


def detect_person(frame):
    """Run MobileNet-SSD, return (box_w, box_h, confidence) for the highest-confidence
    person detection, or None if no person found above CONF_THRESH."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    detections = net.forward()

    best = None
    for i in range(detections.shape[2]):
        conf = detections[0, 0, i, 2]
        class_id = int(detections[0, 0, i, 1])
        if class_id == PERSON_CLASS_ID and conf > CONF_THRESH:
            if best is None or conf > best[0]:
                box = detections[0, 0, i, 3:7] * [w, h, w, h]
                best = (conf, box)

    if best is None:
        return None

    conf, box = best
    x1, y1, x2, y2 = box.astype(int)
    bw, bh = max(x2 - x1, 1), max(y2 - y1, 1)
    return bw, bh, conf


@app.route('/fall_frame', methods=['POST'])
def receive_frame():
    img_array = np.frombuffer(request.data, dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if frame is None:
        return {'status': 'error', 'reason': 'decode_failed'}, 400

    result = detect_person(frame)

    if result is None:
        print("[fall_test] no person detected")
        return {'status': 'no_person'}

    bw, bh, conf = result
    aspect_ratio = bw / bh
    fallen = aspect_ratio > FALL_ASPECT_RATIO
    status = "possible_fall" if fallen else "upright"

    print(f"[fall_test] box=({bw}x{bh}) aspect_ratio={aspect_ratio:.2f} conf={conf:.2f} status={status}")

    if fallen:
        alerted = maybe_alert(frame, aspect_ratio)
        if alerted:
            print("[fall_test] Telegram alert triggered")
        else:
            print("[fall_test] Telegram alert skipped (cooldown)")

    return {'status': status, 'aspect_ratio': round(aspect_ratio, 2), 'confidence': round(float(conf), 2)}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)