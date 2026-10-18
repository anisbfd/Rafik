"""
config.py

Single source of truth for every tunable setting in the health companion.
Nothing outside this file should hardcode a threshold, pin, or timing value.

If a value needs tuning during testing (e.g. FINGER_PRESENT_THRESHOLD),
this is the only file you should need to touch.
"""

# =========================
# I2C addresses
# =========================
OLED_I2C_ADDR = 0x3C
# MAX30102 (0x57) and MLX90614 (0x5A) addresses are fixed inside their
# respective driver libraries, listed here only for reference.

# =========================
# Display
# =========================
OLED_WIDTH = 128
OLED_HEIGHT = 64
DISCLAIMER_TEXT = "Reference only - not diagnostic"

# =========================
# Session flow (guided measurement steps)
# =========================
FINGER_STABLE_SECONDS = 1.0        # finger must be detected for this long before measuring starts
STATUS_POLL_SECONDS = 0.3          # how often we check "is a finger there yet" while waiting
PROGRESS_UPDATE_SECONDS = 0.5      # how often the progress bar redraws during measurement

TEMP_SAMPLE_INTERVAL_SECONDS = 0.5  # how often we poll the MLX90614 while waiting for a reading
TEMP_STABLE_READS = 3                # consecutive plausible readings required before accepting
TEMP_TIMEOUT_SECONDS = 20            # give up and re-prompt if no stable reading found in time

RESULTS_HOLD_SECONDS = 6           # how long each result screen stays up before moving on

# =========================
# MAX30102 / PPG signal
# =========================
SAMPLE_RATE_HZ = 25                # effective FIFO output rate, NOT the raw ADC rate.
                                    # max30102.py configures SPO2_CONFIG=0x27 (100Hz ADC rate)
                                    # AND FIFO_CONFIG=0x4f (4x sample averaging), and averaging
                                    # divides the actual FIFO push rate: 100 / 4 = 25 Hz.
                                    # Using 100 here (the raw ADC rate) was inflating BPM.
WINDOW_SECONDS = 6
WINDOW_SIZE = SAMPLE_RATE_HZ * WINDOW_SECONDS

MIN_BPM, MAX_BPM = 40, 180
BANDPASS_LOW_HZ = 0.7               # ~42 BPM
BANDPASS_HIGH_HZ = 3.5              # ~210 BPM
FILTER_ORDER = 3

BPM_PEAK_PROMINENCE_FRACTION = 0.5   # a candidate peak must rise at least this
                                      # fraction of the window's own peak-to-peak
                                      # amplitude to count as a real heartbeat --
                                      # rejects the dicrotic notch, which was being
                                      # double-counted as a second peak per beat
                                      # (start here; lower it a bit if real beats
                                      # start getting missed, raise it if the
                                      # notch is still slipping through)

FINGER_PRESENT_THRESHOLD = 50_000   # raw IR DC below this = no finger
MIN_PERFUSION_INDEX = 0.0015        # AC/DC ratio below this = signal too weak to trust
                                     # calibrated against real hardware: a good finger
                                     # reading on this sensor measured ~0.0022

# SpO2 ratio-of-ratios is only physiologically valid in this band;
# outside it, treat the reading as untrustworthy rather than clamping.
SPO2_RATIO_MIN = 0.3
SPO2_RATIO_MAX = 1.5

# =========================
# MLX90614 / temperature
# =========================
TEMP_MIN_PLAUSIBLE_C = 30.0
TEMP_MAX_PLAUSIBLE_C = 42.0
TEMP_STABILITY_TOLERANCE_C = 0.4    # consecutive readings must be within this of each other
TEMP_FEVER_THRESHOLD_C = 37.5
TEMP_HIGH_FEVER_THRESHOLD_C = 38.5

# =========================
# Kalman filter tuning
# =========================
# process_variance: how much the true value is expected to drift between
#   readings (higher = trusts new measurements more, faster but noisier)
# measurement_variance: how noisy each raw measurement is believed to be
#   (higher = trusts its own prediction more, smoother but slower to react)
BPM_PROCESS_VARIANCE = 0.5
BPM_MEASUREMENT_VARIANCE = 8.0
SPO2_PROCESS_VARIANCE = 0.05
SPO2_MEASUREMENT_VARIANCE = 4.0

# =========================
# Timing
# =========================
MAIN_LOOP_SLEEP_SECONDS = 0.005    # tight poll for draining the FIFO promptly

# =========================
# Presence detection (laptop webcam proof-of-concept)
# =========================
PRESENCE_SERVER_PORT = 5001
PRESENCE_STALE_SECONDS = 5        # ignore a detection result older than this

# =========================
# Always-on idle loop / reminders
# =========================
IDLE_TICK_SECONDS = 0.1                    # how often the idle loop checks for a due reminder / updates the animation
REMINDERS_FILE = "reminders.json"          # persisted so reminders survive a reboot
TELEGRAM_POLL_TIMEOUT_SECONDS = 25         # Telegram long-poll timeout for the reminder bot
DIAGNOSIS_PRESENCE_TIMEOUT_SECONDS = 300   # give up waiting for someone to sit down after a
                                            # reminder fires, and notify via Telegram instead of
                                            # blocking the idle loop indefinitely
DIAGNOSIS_MAX_FINGER_RETRIES = 3           # if the finger is removed mid-measurement, how many
                                            # times to loop back and retry before giving up

                                    