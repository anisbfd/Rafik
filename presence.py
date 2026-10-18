"""
presence.py

Runs a small Flask server in a background thread that receives JPEG
frames from a laptop webcam (proof-of-concept stand-in for a future
onboard camera module) and runs face detection on each one.

main.py reads the latest result through PresenceDetector.face_present(),
which is thread-safe -- no second process, no polling a file.
"""

import threading
import time

import cv2
import numpy as np
from flask import Flask, request
from werkzeug.serving import WSGIRequestHandler, make_server

import config

WSGIRequestHandler.address_string = lambda self: self.client_address[0]


class PresenceDetector:
    def __init__(self):
        self._lock = threading.Lock()
        self._face_detected = False
        self._last_update = 0.0
        self._active = True

        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        self._app = Flask(__name__)
        self._app.add_url_rule("/frame", "frame", self._receive_frame, methods=["POST"])

        self._server = make_server("0.0.0.0", config.PRESENCE_SERVER_PORT, self._app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        print(f"Presence detector listening on port {config.PRESENCE_SERVER_PORT}")

    def stop(self):
        self._server.shutdown()
    
    def pause(self):
        """Stop running face detection -- used while a session is in
        progress, so the CV thread doesn't compete with the tight I2C
        polling loop for CPU."""
        with self._lock:
            self._active = False
        print("Presence detector paused.")

    def resume(self):
        with self._lock:
            self._active = True
            self._last_update = 0.0  # force face_present() to read as stale until a fresh frame arrives
        print("Presence detector resumed.")

    def _receive_frame(self):

        with self._lock:
            active = self._active

        if not active:
            return {"face_detected": False, "paused": True}

        img_array = np.frombuffer(request.data, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if frame is None:
            return {"face_detected": False, "error": "decode_failed"}, 400

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
        detected = len(faces) > 0

        with self._lock:
            self._face_detected = detected
            self._last_update = time.time()

        return {"face_detected": detected, "count": len(faces)}

    def face_present(self):
        """
        True only if a face was detected AND the last frame arrived
        recently. Without the staleness check, a wifi drop or a closed
        laptop script would leave a stale "True" that wedges the
        session loop waiting on presence that isn't really there.
        """
        with self._lock:
            if time.time() - self._last_update > config.PRESENCE_STALE_SECONDS:
                return False
            return self._face_detected