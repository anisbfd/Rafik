"""
processing.py

Turns raw PPG samples into a BPM and SpO2 reading. This is almost
entirely your original signal-processing logic -- bandpass filter,
peak detection, ratio-of-ratios SpO2 -- just cleaned up and using
config.py for every threshold instead of hardcoded numbers.

One safety fix kept from the rebuild: the SpO2 ratio is sanity-checked
BEFORE going into the empirical formula, so a bad window produces
"no reading" instead of a clamped 0% or 100% that looks like a
medical emergency.
"""

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

import config


def bandpass_filter(signal, fs):
    """
    Isolates the physiological pulse band (0.7-3.5 Hz by default) and
    removes slow drift + high-frequency noise that would otherwise
    confuse peak detection.
    """
    nyq = fs / 2
    b, a = butter(
        config.FILTER_ORDER,
        [config.BANDPASS_LOW_HZ / nyq, config.BANDPASS_HIGH_HZ / nyq],
        btype="band",
    )
    return filtfilt(b, a, signal)


def quick_finger_check(ir_samples):
    """
    A fast, rough check for "is a finger on the sensor right now" -- used
    while waiting for a patient to place their finger, before we have a
    full window to run the real signal-quality check on.
    Just looks at raw IR brightness, no filtering needed.
    """
    if not ir_samples:
        return False
    return np.mean(ir_samples) > config.FINGER_PRESENT_THRESHOLD


def check_signal_quality(ir_raw, ir_ac):
    """
    Returns (is_ok, reason). Rejects a window if no finger is present,
    or if the pulse signal is too weak to trust (poor contact, motion).
    """
    dc = np.mean(ir_raw)
    if dc < config.FINGER_PRESENT_THRESHOLD:
        return False, "no finger detected"

    perfusion_index = ir_ac / dc if dc else 0
    if perfusion_index < config.MIN_PERFUSION_INDEX:
        return False, "weak signal"

    return True, "ok"


def compute_bpm(ir_filtered, fs):
    """
    Counts peaks in the filtered signal and converts spacing to BPM.

    prominence is required in addition to distance: without it, find_peaks
    also catches the dicrotic notch (a smaller secondary bump right after
    the main systolic peak, from the aortic valve closing) as its own peak.
    That silently doubles the counted rate -- this is the classic cause of
    PPG BPM reading ~2x the true resting rate. Requiring each peak to stand
    out by BPM_PEAK_PROMINENCE_FRACTION of the window's own amplitude keeps
    the real systolic peaks while rejecting the notch.
    """
    min_distance = int(fs * 60 / config.MAX_BPM)
    min_prominence = config.BPM_PEAK_PROMINENCE_FRACTION * np.ptp(ir_filtered)
    peaks, _ = find_peaks(ir_filtered, distance=min_distance, prominence=min_prominence)

    if len(peaks) < 3:
        return None

    intervals = np.diff(peaks) / fs
    bpm = 60 / np.mean(intervals)

    if config.MIN_BPM <= bpm <= config.MAX_BPM:
        return bpm
    return None


def compute_spo2(ir_raw, red_raw, ir_filtered, red_filtered):
    """
    Standard ratio-of-ratios pulse-oximetry formula:
        R = (AC_red / DC_red) / (AC_ir / DC_ir)
        SpO2 = 110 - 25 * R

    R is only valid in roughly the 0.3-1.5 range -- outside that band
    the formula's assumptions break down, so we return None (no
    reading) rather than clamp to a 0% or 100% that could be
    misread as a medical emergency.
    """
    ir_dc = np.mean(ir_raw)
    red_dc = np.mean(red_raw)
    ir_ac = np.std(ir_filtered)
    red_ac = np.std(red_filtered)

    if ir_dc == 0 or red_dc == 0 or ir_ac == 0:
        return None

    ratio = (red_ac / red_dc) / (ir_ac / ir_dc)

    if not (config.SPO2_RATIO_MIN <= ratio <= config.SPO2_RATIO_MAX):
        return None

    spo2 = 110 - 25 * ratio
    return max(0.0, min(100.0, spo2))


def analyze_window(ir_samples, red_samples, fs):
    """
    Runs the full pipeline on one window of raw samples.
    Returns (bpm, spo2, status) where bpm/spo2 are None if not
    trustworthy, and status is a short human-readable reason.

    Prints the underlying signal stats every time -- this is what lets
    you calibrate FINGER_PRESENT_THRESHOLD, MIN_PERFUSION_INDEX, and the
    SpO2 ratio bounds in config.py against what your actual sensor sees,
    instead of guessing. Once things are reliable, you can remove or
    comment out this print.
    """
    ir_arr = np.array(ir_samples, dtype=float)
    red_arr = np.array(red_samples, dtype=float)

    ir_filtered = bandpass_filter(ir_arr, fs)
    red_filtered = bandpass_filter(red_arr, fs)

    ir_dc = np.mean(ir_arr)
    red_dc = np.mean(red_arr)
    ir_ac = np.std(ir_filtered)
    red_ac = np.std(red_filtered)
    perfusion_index = (ir_ac / ir_dc) if ir_dc else 0
    ratio = (red_ac / red_dc) / (ir_ac / ir_dc) if (ir_dc and red_dc and ir_ac) else None

    print(
        f"[debug] ir_dc={ir_dc:.0f} red_dc={red_dc:.0f} "
        f"perfusion_index={perfusion_index:.5f} ratio={ratio}"
    )

    ok, reason = check_signal_quality(ir_arr, ir_ac)
    if not ok:
        return None, None, reason

    bpm = compute_bpm(ir_filtered, fs)
    spo2 = compute_spo2(ir_arr, red_arr, ir_filtered, red_filtered)

    return bpm, spo2, "ok"


class SmoothedValue:
    """
    A simple Kalman filter for smoothing one noisy number (BPM or SpO2)
    over time, so the display doesn't jump around between readings.

    process_variance: how much the true value can drift between
        readings (higher = reacts faster to real change, but noisier)
    measurement_variance: how noisy each raw reading is assumed to be
        (higher = trusts its own past estimate more, smoother but slower)
    """

    def __init__(self, process_variance, measurement_variance):
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.estimate = None
        self.error_estimate = None

    def update(self, measurement):
        if self.estimate is None:
            self.estimate = measurement
            self.error_estimate = self.measurement_variance
            return self.estimate

        predicted_estimate = self.estimate
        predicted_error = self.error_estimate + self.process_variance

        gain = predicted_error / (predicted_error + self.measurement_variance)
        self.estimate = predicted_estimate + gain * (measurement - predicted_estimate)
        self.error_estimate = (1 - gain) * predicted_error

        return self.estimate