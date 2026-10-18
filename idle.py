"""
idle.py

VitalBot's "alive" behavior while it's just sitting there waiting for
the next scheduled diagnosis -- occasional blinks and mood shifts so
it doesn't look frozen. Deliberately throttled: it only pushes a new
frame to the OLED when something actually changes, not on every tick,
since I2C writes aren't free and this runs all day.
"""

import random
import time

# Idle cycles through these -- deliberately excludes "thinking"/"worried",
# which are reserved for states where something is actually happening.
IDLE_MOODS = ["alert", "alert", "happy", "sleepy"]  # alert weighted more likely


class IdleAnimator:
    def __init__(self, blink_min=3.0, blink_max=8.0, mood_min=15.0, mood_max=40.0):
        self._blink_min = blink_min
        self._blink_max = blink_max
        self._mood_min = mood_min
        self._mood_max = mood_max

        self._mood = "alert"
        self._next_blink = time.time() + random.uniform(blink_min, blink_max)
        self._next_mood_change = time.time() + random.uniform(mood_min, mood_max)
        self._blinking_until = 0
        self._last_pushed = None  # (mood, is_blinking) of the last frame actually drawn

    def tick(self, oled):
        now = time.time()

        if now >= self._next_mood_change:
            self._mood = random.choice(IDLE_MOODS)
            self._next_mood_change = now + random.uniform(self._mood_min, self._mood_max)

        is_blinking = now < self._blinking_until

        if not is_blinking and now >= self._next_blink:
            self._blinking_until = now + 0.15  # a blink is quick
            self._next_blink = now + random.uniform(self._blink_min, self._blink_max)
            is_blinking = True

        frame_state = (self._mood, is_blinking)
        if frame_state != self._last_pushed:
            display_mood = "sleepy" if is_blinking else self._mood
            oled.show_idle(display_mood)
            self._last_pushed = frame_state