"""
display.py

VitalBot's face is now just a pair of expressive eyes, full-screen.
Text-heavy screens (results) keep a small eye icon plus the numbers --
everything else (waiting, prompts, progress) is eyes-only.

Moods: 'sleepy', 'alert', 'thinking', 'happy', 'worried'
"""

from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

import config


class OledDisplay:
    def __init__(self, i2c_bus):
        self._oled = adafruit_ssd1306.SSD1306_I2C(
            config.OLED_WIDTH, config.OLED_HEIGHT, i2c_bus, addr=config.OLED_I2C_ADDR
        )
        self._font = ImageFont.load_default()
        self.clear()

    def clear(self):
        self._oled.fill(0)
        self._oled.show()

    def show_message(self, lines, mood="alert"):
        """Full-screen eyes with a short caption underneath."""
        image = self._new_frame()
        draw = ImageDraw.Draw(image)

        self._draw_eyes(draw, mood, eye_top=2, eye_h=32)

        y = 40
        for line in lines[:2]:
            draw.text((0, y), line[:21], font=self._font, fill=255)
            y += 10

        self._push(image)

    def show_idle(self, mood="alert"):
        """Full-screen eyes, no text -- VitalBot's resting/idle face."""
        image = self._new_frame()
        draw = ImageDraw.Draw(image)

        self._draw_eyes(draw, mood, eye_top=16, eye_h=32)

        self._push(image)

    def show_progress(self, message, fraction, mood="thinking"):
        """Smaller eyes up top, progress bar below."""
        image = self._new_frame()
        draw = ImageDraw.Draw(image)

        self._draw_eyes(draw, mood, eye_top=0, eye_h=20)

        draw.text((0, 24), message[:21], font=self._font, fill=255)

        bar_x, bar_y, bar_w, bar_h = 4, 36, 120, 10
        fraction = max(0.0, min(1.0, fraction))
        draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), outline=255)
        fill_w = int(bar_w * fraction)
        if fill_w > 0:
            draw.rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=255)

        draw.text((90, 36), f"{int(fraction * 100)}%", font=self._font, fill=255)

        self._push(image)

    def show_results(self, bpm, spo2, object_temp):
        """Numbers, with a small happy-eyes icon up top."""
        image = self._new_frame()
        draw = ImageDraw.Draw(image)

        self._draw_eyes(draw, "happy", eye_top=0, eye_h=12, cx=114, spacing=10)
        draw.text((0, 0), "VitalBot says:", font=self._font, fill=255)

        draw.text((0, 16), "BPM:", font=self._font, fill=255)
        draw.text((50, 16), self._format_number(bpm, "{:.0f}"), font=self._font, fill=255)

        draw.text((0, 28), "SpO2:", font=self._font, fill=255)
        draw.text((50, 28), self._format_number(spo2, "{:.0f}%"), font=self._font, fill=255)

        draw.text((0, 40), "Temp:", font=self._font, fill=255)
        draw.text((50, 40), self._format_temp(object_temp), font=self._font, fill=255)

        draw.text((0, 54), config.DISCLAIMER_TEXT[:21], font=self._font, fill=255)

        self._push(image)

    def _draw_eyes(self, draw, mood, eye_top, eye_h, cx=64, spacing=34):
        """
        Draws a pair of eyes centered at cx, spacing apart, eye_h tall.
        This is the one place all facial expression logic lives -- add
        new moods here as VitalBot grows (e.g. a 'talking' mood later
        that bounces eye_h on a timer for lip-sync-style feedback).
        """
        eye_w = int(eye_h * 0.7)
        left_x = cx - spacing
        right_x = cx + spacing

        if mood == "sleepy":
            # thin closed lines
            for x in (left_x, right_x):
                draw.line((x - eye_w // 2, eye_top + eye_h // 2,
                           x + eye_w // 2, eye_top + eye_h // 2), fill=255, width=2)

        elif mood == "thinking":
            # eyes shifted, one squinted
            for x, squint in ((left_x, False), (right_x, True)):
                h = eye_h // 2 if squint else eye_h
                draw.rounded_rectangle(
                    (x - eye_w // 2, eye_top + (eye_h - h) // 2,
                     x + eye_w // 2, eye_top + (eye_h - h) // 2 + h),
                    radius=eye_w // 3, fill=255,
                )

        elif mood == "happy":
            # upward curves, like ^ ^
            for x in (left_x, right_x):
                draw.arc(
                    (x - eye_w // 2, eye_top, x + eye_w // 2, eye_top + eye_h),
                    start=200, end=340, fill=255, width=3,
                )

        elif mood == "worried":
            # angled inward, like a concerned brow
            for x, tilt in ((left_x, 1), (right_x, -1)):
                draw.rounded_rectangle(
                    (x - eye_w // 2, eye_top + max(0, tilt * 4),
                     x + eye_w // 2, eye_top + eye_h - max(0, -tilt * 4)),
                    radius=eye_w // 3, fill=255,
                )

        else:  # "alert" -- default, wide open
            for x in (left_x, right_x):
                draw.rounded_rectangle(
                    (x - eye_w // 2, eye_top, x + eye_w // 2, eye_top + eye_h),
                    radius=eye_w // 3, fill=255,
                )

    def _new_frame(self):
        return Image.new("1", (config.OLED_WIDTH, config.OLED_HEIGHT))

    def _push(self, image):
        self._oled.image(image)
        self._oled.show()

    @staticmethod
    def _format_number(value, fmt):
        return fmt.format(value) if value is not None else "--"

    @staticmethod
    def _format_temp(value):
        return f"{value:.1f}C" if value is not None else "--"