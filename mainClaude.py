"""
main.py

VitalBot health companion main controller

Flow:
1. Detect person
2. Voice greeting
3. Wait for finger on MAX30102
4. Measure heart rate + SpO2
5. Measure temperature
6. Display results
"""

import time
import threading
from collections import deque

import board
import busio

import config

from sensors import PulseOxSensor, TemperatureSensor
from processing import analyze_window, quick_finger_check
from display import OledDisplay
from presence import PresenceDetector

from voice import precache

from health_voice import (
    ALL_PHRASES,
    start_health_check,
    ask_finger,
    finger_lost,
    no_finger_timeout,
    heart_finished,
    ask_temperature,
    finished
)


# =========================
# Keep MAX30102 alive
# =========================

def pause_while_draining(pulse_ox, seconds):

    end = time.time() + seconds

    while time.time() < end:

        pulse_ox.read_samples()

        time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)


def speak_while_draining(pulse_ox, speak_func, *args):
    """
    Runs a blocking speak_func on a separate thread while draining the
    pulse_ox FIFO on the main thread. Prevents the MAX30102's
    32-sample buffer from overflowing during TTS playback.
    """
    thread = threading.Thread(target=speak_func, args=args)
    thread.start()

    while thread.is_alive():
        pulse_ox.read_samples()
        time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)

    thread.join()


def announce(pulse_ox, oled, lines, mood, speak_func, *args):
    """
    Updates the OLED and starts talking in the same instant, so voice
    and screen move together instead of the screen lagging or freezing
    on a stale frame while speech plays.
    """
    oled.show_message(lines, mood=mood)
    speak_while_draining(pulse_ox, speak_func, *args)


# =========================
# Presence detection
# =========================

def wait_for_presence(pulse_ox, presence, oled):

    oled.show_message(
        ["Hi, I'm VitalBot!", "Looking for you..."],
        mood="sleepy"
    )

    presence.resume()

    while True:

        pulse_ox.read_samples()

        if presence.face_present():

            print("Presence confirmed.")

            speak_while_draining(pulse_ox, start_health_check)

            presence.pause()

            return True

        time.sleep(config.STATUS_POLL_SECONDS)


# =========================
# Finger detection
# =========================

def wait_for_finger(pulse_ox, oled, greet=False):

    if greet:
        announce(
            pulse_ox, oled,
            ["Found you!", "Place finger"],
            "happy",
            ask_finger
        )
    else:
        oled.show_message(["Place finger"], mood="happy")

    # announce(
    #     pulse_ox, oled,
    #     ["Found you!", "Place finger"],
    #     "happy",
    #     ask_finger
    # )

    recent_ir = deque(maxlen=int(config.SAMPLE_RATE_HZ * 0.5))
    stable_since = None
    start_time = time.time()

    print("Waiting for finger...")

    while True:

        samples = pulse_ox.read_samples()

        for _red, ir in samples:
            recent_ir.append(ir)
            print("IR:", ir)

        finger = quick_finger_check(list(recent_ir))

        if finger:

            if stable_since is None:
                stable_since = time.time()

            elif time.time() - stable_since >= config.FINGER_STABLE_SECONDS:

                print("Finger detected!")

                oled.show_message(
                    ["Finger detected", "Measuring..."],
                    mood="thinking"
                )

                return True

        else:
            stable_since = None

        if time.time() - start_time > 30:

            print("Finger timeout")

            announce(
                pulse_ox, oled,
                ["No finger", "Try again"],
                "worried",
                no_finger_timeout
            )

            return False

        time.sleep(config.STATUS_POLL_SECONDS)


# =========================
# Heart measurement
# =========================

def measure_vitals(pulse_ox, oled):

    ir_buffer = deque(maxlen=config.WINDOW_SIZE)
    red_buffer = deque(maxlen=config.WINDOW_SIZE)
    recent_ir = deque(maxlen=int(config.SAMPLE_RATE_HZ * 0.5))
    last_update = 0

    while len(ir_buffer) < config.WINDOW_SIZE:

        for red, ir in pulse_ox.read_samples():
            print("MEASURE IR:", ir)
            ir_buffer.append(ir)
            red_buffer.append(red)
            recent_ir.append(ir)

        if recent_ir and not quick_finger_check(list(recent_ir)):

            print("Finger removed")

            announce(
                pulse_ox, oled,
                ["Finger lost", "Place it back"],
                "worried",
                finger_lost
            )

            pause_while_draining(pulse_ox, 1)

            return None, None

        now = time.time()

        if now - last_update >= config.PROGRESS_UPDATE_SECONDS:
            last_update = now
            oled.show_progress(
                "Measuring...",
                len(ir_buffer) / config.WINDOW_SIZE,
                mood="thinking"
            )

        time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)

    bpm, spo2, status = analyze_window(
        list(ir_buffer), list(red_buffer), config.SAMPLE_RATE_HZ
    )

    print("RESULT:", bpm, spo2, status)

    if status != "ok":

        oled.show_message(
            ["Reading unclear", "Try again"],
            mood="worried"
        )

        return None, None

    return bpm, spo2


# =========================
# Temperature
# =========================

def measure_temperature(pulse_ox, temp_sensor, oled):
    """
    NOTE: progress feedback reuses show_progress(), so it currently
    looks the same as the heart-rate bar. A distinct visual style
    needs display.py -- not guessing at that API without seeing it.
    """

    stable = 0
    last_temp = None
    start = time.time()

    while time.time() - start < config.TEMP_TIMEOUT_SECONDS:

        pulse_ox.read_samples()

        temp, ambient = temp_sensor.read_temperature()

        if temp is not None:

            print("TEMP:", temp)

            if last_temp and abs(temp - last_temp) <= config.TEMP_STABILITY_TOLERANCE_C:
                stable += 1
            else:
                stable = 1

            last_temp = temp

            oled.show_progress(
                "Checking temp...",
                min(stable / config.TEMP_STABLE_READS, 1.0),
                mood="alert"
            )

            if stable >= config.TEMP_STABLE_READS:
                return temp

        time.sleep(config.TEMP_SAMPLE_INTERVAL_SECONDS)

    return None


# =========================
# Main
# =========================

def main():

    i2c = busio.I2C(board.SCL, board.SDA)

    pulse_ox = PulseOxSensor()
    temp_sensor = TemperatureSensor(i2c)
    oled = OledDisplay(i2c)

    presence = PresenceDetector()
    presence.start()

    oled.show_message(["Warming up", "my voice..."], mood="sleepy")
    precache(ALL_PHRASES)

    print("Health monitor running.")

    try:

        while True:

            wait_for_presence(pulse_ox, presence, oled)

            # Inner loop: once a person is present, stay in the
            # finger/measurement cycle. A lost finger mid-measurement
            # loops back to wait_for_finger directly -- it does NOT
            # drop back out to presence detection. Presence is only
            # re-checked if no finger is ever placed (person likely
            # walked away) or after a full successful measurement.
            first_attempt = True
            while True:

                finger = wait_for_finger(pulse_ox, oled, greet=first_attempt)
                first_attempt = False

                if not finger:
                    # nobody placed a finger at all -- assume they left
                    break

                print("START HEART")

                bpm, spo2 = measure_vitals(pulse_ox, oled)

                print("HEART:", bpm, spo2)

                if bpm is None:
                    # finger was placed then lost -- retry finger step,
                    # not presence detection
                    continue

                announce(
                    pulse_ox, oled,
                    ["Heart check", "complete!"],
                    "happy",
                    heart_finished
                )

                announce(
                    pulse_ox, oled,
                    ["Point sensor", "to forehead"],
                    "alert",
                    ask_temperature
                )

                temp = measure_temperature(pulse_ox, temp_sensor, oled)

                oled.show_results(bpm, spo2, temp)

                speak_while_draining(pulse_ox, finished)

                pause_while_draining(pulse_ox, config.RESULTS_HOLD_SECONDS)

                break

    except KeyboardInterrupt:

        print("Stopping...")
        presence.stop()
        oled.clear()


if __name__ == "__main__":

    main()