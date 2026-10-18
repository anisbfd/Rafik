# """
# main.py

# Runs one guided measurement session per patient, on a loop:

#     1. Wait for presence (webcam proof-of-concept)
#     2. Wait for a finger on the pulse-ox sensor
#     3. Capture a clean 6-second window, showing progress
#     4. Wait for a stable temperature reading
#     5. Show the combined result, hold it on screen
#     6. Go back to step 1 for the next patient

# Run with:
#     python3 main.py
# Stop with Ctrl+C (the OLED clears itself on exit).
# """

# import time
# from collections import deque

# import board
# import busio

# import config
# from sensors import PulseOxSensor, TemperatureSensor
# from processing import analyze_window, quick_finger_check
# from display import OledDisplay
# from presence import PresenceDetector

# from health_voice import (
#     start_health_check,
#     ask_finger,
#     heart_finished,
#     ask_temperature,
#     finished
# )


# def pause_while_draining(pulse_ox, seconds):
#     """
#     Pauses for the given duration, but keeps draining the pulse-ox FIFO
#     the entire time. A blind time.sleep() here would leave the MAX30102's
#     32-sample FIFO unread -- at the sensor's ~25Hz effective rate that
#     overflows in about 1.3 seconds, which can leave it stuck returning no
#     data on the next measurement attempt.
#     """
#     pause_until = time.time() + seconds
#     while time.time() < pause_until:
#         pulse_ox.read_samples()  # discarded -- just keeps the FIFO from overflowing
#         time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)


# def wait_for_presence(pulse_ox, presence, oled):
#     """
#     Blocks until the webcam pipeline confirms someone is at the desk.
#     Keeps draining the pulse-ox FIFO the whole time it waits -- otherwise
#     the MAX30102's 32-sample buffer overflows in ~1.3s and wedges the
#     sensor for the finger-detection step that follows.
#     """
#     oled.show_message(["Hi, I'm VitalBot!", "Looking for you..."], mood="sleepy")
#     presence.resume()

#     while True:
#         pulse_ox.read_samples()  # discarded -- just keeps the FIFO from overflowing

#         if presence.face_present():
#             print("Presence confirmed.")
#             start_health_check()
#             presence.pause()
#             return
#         time.sleep(config.STATUS_POLL_SECONDS)


# # def wait_for_finger(pulse_ox, oled):
# #     """Blocks until a finger is detected and stays detected for a moment
# #     (avoids triggering on a brief accidental touch)."""
# #     oled.show_message(["Found you!", "Pop a finger on my sensor"], mood="happy")
# #     ask_finger()

# #     recent_ir = deque(maxlen=int(config.SAMPLE_RATE_HZ * 0.5))
# #     stable_since = None

# #     while True:
# #         for _red, ir in pulse_ox.read_samples():
# #             recent_ir.append(ir)

# #         if quick_finger_check(list(recent_ir)):
# #             if stable_since is None:
# #                 stable_since = time.time()
# #             elif time.time() - stable_since >= config.FINGER_STABLE_SECONDS:
# #                 print("Finger detected, starting measurement.")
# #                 return
# #         else:
# #             stable_since = None

# #         time.sleep(config.STATUS_POLL_SECONDS)
# def wait_for_finger(pulse_ox, oled):
#     """
#     Wait until MAX30102 detects a finger.
#     """

#     oled.show_message(
#         ["Found you!", "Place finger"],
#         mood="happy"
#     )

#     ask_finger()

#     recent_ir = deque(
#         maxlen=int(config.SAMPLE_RATE_HZ * 0.5)
#     )

#     stable_since = None
#     start_time = time.time()

#     print("Waiting for finger...")

#     while True:

#         samples = pulse_ox.read_samples()

#         for _red, ir in samples:
#             recent_ir.append(ir)

#             # DEBUG
#             print("IR:", ir)

#         detected = quick_finger_check(
#             list(recent_ir)
#         )

#         if detected:

#             if stable_since is None:
#                 stable_since = time.time()

#             elif time.time() - stable_since >= config.FINGER_STABLE_SECONDS:

#                 print("Finger detected!")
#                 oled.show_message(
#                     ["Finger detected",
#                      "Measuring..."],
#                     mood="thinking"
#                 )

#                 return True

#         else:
#             stable_since = None


#         # timeout after 30 seconds
#         if time.time() - start_time > 30:

#             print("Finger timeout")

#             oled.show_message(
#                 ["No finger",
#                  "Try again"],
#                 mood="worried"
#             )

#             return False


#         time.sleep(
#             config.STATUS_POLL_SECONDS
#         )


# def measure_vitals(pulse_ox, oled):
#     """
#     Captures one fresh window of samples and analyzes it.
#     Returns (bpm, spo2) on success, or (None, None) if the finger was
#     removed mid-measurement or the reading wasn't trustworthy.
#     """
#     ir_buffer = deque(maxlen=config.WINDOW_SIZE)
#     red_buffer = deque(maxlen=config.WINDOW_SIZE)
#     recent_ir = deque(maxlen=int(config.SAMPLE_RATE_HZ * 0.5))
#     last_progress_update = 0

#     while len(ir_buffer) < config.WINDOW_SIZE:
#         for red, ir in pulse_ox.read_samples():
#             ir_buffer.append(ir)
#             red_buffer.append(red)
#             recent_ir.append(ir)

#         if recent_ir and not quick_finger_check(list(recent_ir)):
#             print("Finger removed mid-measurement, aborting.")
#             oled.show_message(["Oops, lost you!", "let's try again"], mood="worried")
#             pause_while_draining(pulse_ox, 1.5)
#             return None, None

#         now = time.time()
#         if now - last_progress_update >= config.PROGRESS_UPDATE_SECONDS:
#             last_progress_update = now
#             oled.show_progress("Measuring...", len(ir_buffer) / config.WINDOW_SIZE, mood="thinking")

#         time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)

#     bpm, spo2, status = analyze_window(list(ir_buffer), list(red_buffer), config.SAMPLE_RATE_HZ)
#     print(f"Measurement result: bpm={bpm} spo2={spo2} status={status}")

#     if status != "ok":
#         oled.show_message(["Reading unclear", "let's try again"], mood="worried")
#         pause_while_draining(pulse_ox, 2)
#         return None, None

#     return bpm, spo2


# def measure_temperature(pulse_ox, temp_sensor, oled):
#     """
#     Waits for a stable, plausible temperature reading.
#     Returns the temperature, or None if no stable reading arrived
#     before the timeout (patient likely didn't position the sensor).

#     "Stable" means several consecutive readings that AGREE with each
#     other (within TEMP_STABILITY_TOLERANCE_C), not just readings that
#     each individually look plausible. Without this, a sensor briefly
#     catching ambient air instead of skin can slip a bad reading through
#     even though each single value looked reasonable on its own.

#     Keeps draining the pulse-ox sensor's FIFO the whole time it waits --
#     the MAX30102's onboard buffer only holds 32 samples (about 0.3s
#     worth at 100Hz), so if nothing reads it during this step it
#     overflows and can leave the sensor stuck returning no data on the
#     next measurement.
#     """
#     oled.show_message(["Now point me at", "your forehead or wrist"], mood="alert")

#     stable_count = 0
#     last_temp = None
#     start_time = time.time()
#     next_sample_time = start_time

#     while time.time() - start_time < config.TEMP_TIMEOUT_SECONDS:
#         pulse_ox.read_samples()  # discarded -- just keeps the FIFO from overflowing

#         now = time.time()
#         if now >= next_sample_time:
#             next_sample_time = now + config.TEMP_SAMPLE_INTERVAL_SECONDS
#             object_temp, _ambient_temp = temp_sensor.read_temperature()

#             if object_temp is not None:
#                 if last_temp is not None and abs(object_temp - last_temp) <= config.TEMP_STABILITY_TOLERANCE_C:
#                     stable_count += 1
#                 else:
#                     stable_count = 1  # start a fresh streak from this reading
#                 last_temp = object_temp

#                 if stable_count >= config.TEMP_STABLE_READS:
#                     print(f"Temperature confirmed: {last_temp:.1f}C")
#                     return last_temp
#             else:
#                 stable_count = 0
#                 last_temp = None

#         time.sleep(config.MAIN_LOOP_SLEEP_SECONDS)

#     print("Temperature reading timed out.")
#     return None


# def main():
#     i2c = busio.I2C(board.SCL, board.SDA)

#     pulse_ox = PulseOxSensor()
#     temp_sensor = TemperatureSensor(i2c)
#     oled = OledDisplay(i2c)

#     presence = PresenceDetector()
#     presence.start()

#     print("Health monitor running. Press Ctrl+C to stop.")

#     try:
#         while True:
#             wait_for_presence(pulse_ox, presence, oled)

#             finger_ok = wait_for_finger(
#             pulse_ox,
#             oled
#             )

#             if not finger_ok:
#                 continue
      
#             print("STARTING HEART MEASUREMENT")

#             bpm, spo2 = measure_vitals(pulse_ox, oled)

#             print("HEART RESULT:", bpm, spo2)
#             if bpm is None:
#                 continue
#             heart_finished()    

#             ask_temperature()
#             temp = measure_temperature(pulse_ox, temp_sensor, oled)

#             oled.show_results(bpm, spo2, temp)
#             finished()
#             pause_while_draining(pulse_ox, config.RESULTS_HOLD_SECONDS)

#     except KeyboardInterrupt:
#         print("\nStopping...")
#         presence.stop()
#         oled.clear()


# if __name__ == "__main__":
#     main()
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
from reminders import ReminderBot
from idle import IdleAnimator

from health_voice import (
    finger_lost,
    start_health_check,
    ask_finger,
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

        time.sleep(
            config.MAIN_LOOP_SLEEP_SECONDS
        )


def speak_while_draining(pulse_ox, speak_func, *args):
    """
    Runs a blocking speak_func (e.g. ask_finger) on a separate thread
    while draining the pulse_ox FIFO on the main thread. Prevents the
    MAX30102's 32-sample buffer from overflowing during TTS playback --
    without this, any call to speak() that isn't drained blows past the
    ~1.3s overflow window and leaves the sensor stuck on the next read.
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

def wait_for_presence(pulse_ox, presence, oled, timeout_seconds=None):
    """
    Blocks until a face is detected, or returns False if timeout_seconds
    elapses first. timeout_seconds=None waits forever (used by the old
    always-looping session flow); a reminder-triggered diagnosis passes
    a real timeout so it doesn't wedge the idle loop if nobody shows up.
    """

    oled.show_message(
        [
            "Hi, I'm VitalBot!",
            "Looking for you..."
        ],
        mood="sleepy"
    )

    presence.resume()

    start = time.time()

    while True:

        pulse_ox.read_samples()

        if presence.face_present():

            print("Presence confirmed.")

            presence.pause()

            return True

        if (
            timeout_seconds is not None
            and time.time() - start > timeout_seconds
        ):
            print("Presence timeout.")
            presence.pause()
            return False

        time.sleep(
            config.STATUS_POLL_SECONDS
        )


# =========================
# Finger detection
# =========================

def wait_for_finger(pulse_ox, oled, greet=True):

    if greet:
        announce(
            pulse_ox, oled,
            ["Found you!", "Place finger"],
            "happy",
            ask_finger
        )
    else:
        # Used when we're looping back here right after finger_lost()
        # already spoke "Finger lost, place it back" -- speaking a
        # second, different prompt (ask_finger) on top of that is what
        # made the transition feel repeated/unsmooth. Just update the
        # screen and start listening again, no extra voice line.
        oled.show_message(
            [
                "Place finger",
                "back on sensor"
            ],
            mood="happy"
        )

    recent_ir = deque(
        maxlen=int(
            config.SAMPLE_RATE_HZ * 0.5
        )
    )

    stable_since = None

    start_time = time.time()

    print("Waiting for finger...")

    while True:

        samples = pulse_ox.read_samples()

        for _red, ir in samples:

            recent_ir.append(ir)

            print(
                "IR:",
                ir
            )

        finger = quick_finger_check(
            list(recent_ir)
        )

        if finger:

            if stable_since is None:

                stable_since = time.time()

            elif (
                time.time()
                -
                stable_since
                >=
                config.FINGER_STABLE_SECONDS
            ):

                print(
                    "Finger detected!"
                )

                oled.show_message(
                    [
                        "Finger detected",
                        "Measuring..."
                    ],
                    mood="thinking"
                )

                return True

        else:

            stable_since = None

        if time.time() - start_time > 30:

            print(
                "Finger timeout"
            )

            oled.show_message(
                [
                    "No finger",
                    "Try again"
                ],
                mood="worried"
            )

            return False

        time.sleep(
            config.STATUS_POLL_SECONDS
        )


# =========================
# Heart measurement
# =========================

def measure_vitals(pulse_ox, oled):
    """
    Returns (bpm, spo2, status). status is "ok", "finger_lost" (the
    finger was physically removed mid-measurement -- caller should
    send the person back to wait_for_finger and retry), or "unclear"
    (a full window was captured but the signal wasn't clean enough to
    trust).
    """

    ir_buffer = deque(
        maxlen=config.WINDOW_SIZE
    )

    red_buffer = deque(
        maxlen=config.WINDOW_SIZE
    )

    recent_ir = deque(
        maxlen=int(
            config.SAMPLE_RATE_HZ * 0.5
        )
    )

    last_update = 0

    while len(ir_buffer) < config.WINDOW_SIZE:

        for red, ir in pulse_ox.read_samples():

            print(
                "MEASURE IR:",
                ir
            )

            ir_buffer.append(ir)

            red_buffer.append(red)

            recent_ir.append(ir)

        if (
            recent_ir
            and
            not quick_finger_check(
                list(recent_ir)
            )
        ):

            print(
                "Finger removed"
            )
            announce(
                pulse_ox, oled,
                ["Finger lost", "Place it back"],
                "worried",
                finger_lost
            )

            pause_while_draining(
                pulse_ox,
                1
            )

            return None, None, "finger_lost"

        now = time.time()

        if (
            now - last_update
            >=
            config.PROGRESS_UPDATE_SECONDS
        ):

            last_update = now

            oled.show_progress(
                "Measuring...",
                len(ir_buffer)
                /
                config.WINDOW_SIZE,
                mood="thinking"
            )

        time.sleep(
            config.MAIN_LOOP_SLEEP_SECONDS
        )

    bpm, spo2, status = analyze_window(
        list(ir_buffer),
        list(red_buffer),
        config.SAMPLE_RATE_HZ
    )

    print(
        "RESULT:",
        bpm,
        spo2,
        status
    )

    if status != "ok":

        oled.show_message(
            [
                "Reading unclear",
                "Try again"
            ],
            mood="worried"
        )

        return None, None, "unclear"

    return bpm, spo2, "ok"


# =========================
# Temperature
# =========================

def measure_temperature(
        pulse_ox,
        temp_sensor,
        oled):

    oled.show_message(
        [
            "Point sensor",
            "to forehead"
        ],
        mood="alert"
    )

    stable = 0

    last_temp = None

    start = time.time()

    while (
        time.time() - start
        <
        config.TEMP_TIMEOUT_SECONDS
    ):

        pulse_ox.read_samples()

        temp, ambient = (
            temp_sensor.read_temperature()
        )

        if temp is not None:

            print(
                "TEMP:",
                temp
            )

            if (
                last_temp
                and
                abs(temp-last_temp)
                <=
                config.TEMP_STABILITY_TOLERANCE_C
            ):

                stable += 1

            else:

                stable = 1

            last_temp = temp

            # Progress reflects the stability streak, since that's
            # what's actually gating an accepted reading -- a single
            # good sample isn't enough, config.TEMP_STABLE_READS
            # consecutive agreeing samples are.
            oled.show_progress(
                "Checking temp...",
                min(stable / config.TEMP_STABLE_READS, 1.0),
                mood="alert"
            )

            if (
                stable
                >=
                config.TEMP_STABLE_READS
            ):

                return temp

        time.sleep(
            config.TEMP_SAMPLE_INTERVAL_SECONDS
        )

    return None


# =========================
# Main
# =========================

# =========================
# One-shot diagnosis (triggered by a due reminder)
# =========================

def run_diagnosis(pulse_ox, temp_sensor, oled, presence, reminders, due_hhmm, label=None):
    """
    Runs exactly one guided measurement pass, then reports back over
    Telegram and returns to idle -- unlike the old always-looping
    session flow, this is meant to be called once per reminder firing
    (or once per /diagnose request, in which case due_hhmm is None).
    """

    label = label or due_hhmm or "on-demand"

    if due_hhmm is not None:
        reminders.mark_fired(due_hhmm)

    announce(
        pulse_ox, oled,
        ["Hi, I'm VitalBot!", "Time to check in"],
        "happy",
        start_health_check
    )

    present = wait_for_presence(
        pulse_ox,
        presence,
        oled,
        timeout_seconds=config.DIAGNOSIS_PRESENCE_TIMEOUT_SECONDS,
    )

    if not present:
        print(f"Diagnosis ({label}): nobody showed up.")
        reminders.send_message(
            f"⏰ {label}: I didn't see anyone, so I skipped "
            f"today's check. Come find me when you're ready."
        )
        oled.clear()
        return

    bpm = spo2 = None
    vitals_status = None

    for attempt in range(config.DIAGNOSIS_MAX_FINGER_RETRIES):

        finger = wait_for_finger(pulse_ox, oled, greet=(attempt == 0))

        if not finger:
            announce(
                pulse_ox, oled,
                ["No finger", "detected"],
                "worried",
                no_finger_timeout
            )
            reminders.send_message(
                f"⏰ {label}: you were there, but I couldn't get "
                f"a steady finger reading. Try again whenever you're ready."
            )
            oled.clear()
            return

        bpm, spo2, vitals_status = measure_vitals(pulse_ox, oled)

        if vitals_status == "ok":
            break

        if vitals_status == "finger_lost":
            # measure_vitals already announced "Finger lost, place it
            # back" -- loop back to wait_for_finger and pick the
            # diagnosis back up instead of giving up on it entirely.
            continue

        # vitals_status == "unclear": a full window was captured but the
        # signal was too noisy to trust. Not a finger-removal issue, so
        # don't keep retrying -- report it and stop.
        reminders.send_message(
            f"⏰ {label}: the heart reading wasn't clean, so "
            f"I couldn't get a result this time."
        )
        oled.clear()
        return

    else:
        # Loop exhausted without ever reaching "ok" -- kept losing the
        # finger every attempt.
        reminders.send_message(
            f"⏰ {label}: kept losing the finger reading, so I stopped "
            f"trying for now. Try again whenever you're ready."
        )
        oled.clear()
        return

    announce(
        pulse_ox, oled,
        ["Heart check", "complete!"],
        "happy",
        heart_finished
    )
    announce(
        pulse_ox, oled,
        ["Now let's check", "your temperature"],
        "alert",
        ask_temperature
    )

    temp = measure_temperature(pulse_ox, temp_sensor, oled)

    oled.show_results(bpm, spo2, temp)

    speak_while_draining(pulse_ox, finished)

    temp_str = f"{temp:.1f}C" if temp is not None else "not captured"
    reminders.send_message(
        f"✅ {label} check-in complete:\n"
        f"BPM: {bpm:.0f}\n"
        f"SpO2: {spo2:.0f}%\n"
        f"Temp: {temp_str}\n\n"
        f"{config.DISCLAIMER_TEXT}"
    )

    pause_while_draining(pulse_ox, config.RESULTS_HOLD_SECONDS)

    oled.clear()


def main():

    i2c = busio.I2C(
        board.SCL,
        board.SDA
    )

    pulse_ox = PulseOxSensor()

    temp_sensor = TemperatureSensor(
        i2c
    )

    oled = OledDisplay(
        i2c
    )

    presence = PresenceDetector()
    presence.start()

    reminders = ReminderBot()
    reminders.start()

    idle_animator = IdleAnimator()

    print(
        "VitalBot running -- idle, waiting on reminders. "
        "Text the bot /remind HH:MM to schedule a check-in."
    )

    try:

        while True:

            due = reminders.get_due_reminder()
            manual = False if due is not None else reminders.pop_manual_request()

            if due is not None or manual:

                label = due if due is not None else "on-demand check-in"
                print(f"Diagnosis triggered: {label}")

                try:
                    run_diagnosis(
                        pulse_ox, temp_sensor, oled, presence, reminders,
                        due_hhmm=due, label=label,
                    )
                except Exception as e:
                    # A single bad sensor read or transient error shouldn't
                    # take down a process meant to run all day -- log it,
                    # let the person know, and go back to idle.
                    print(f"[main] diagnosis run failed: {e}")
                    reminders.send_message(
                        f"⚠️ Something went wrong running the {label} check-in. "
                        f"I'm back to normal now."
                    )
                    presence.pause()
                    oled.clear()

            else:

                pulse_ox.read_samples()  # discarded -- idle can run for hours between
                                          # reminders, and the FIFO overflows/freezes
                                          # in ~1.3s if nothing drains it in the meantime
                idle_animator.tick(oled)
                time.sleep(config.IDLE_TICK_SECONDS)

    except KeyboardInterrupt:

        print(
            "Stopping..."
        )

        presence.stop()
        reminders.stop()

        oled.clear()


if __name__ == "__main__":

    main()