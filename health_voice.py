from voice import speak
from sound import play_sound
from language import get_language


def say(english_text, arabic_file):

    if get_language() == "ar":
        play_sound("sounds/" + arabic_file)
    else:
        speak(english_text)


GREETING = "Hello. It is time for your daily health check."

ASK_FINGER = "Please place your finger on the heart sensor and keep still."

FINGER_LOST = "It looks like I lost your finger. Please place it back and keep still."

NO_FINGER_TIMEOUT = "I could not find your finger. Let's try again."

HEART_FINISHED = "Your heart measurement is complete."

ASK_TEMPERATURE = "Now, please place your forehead near the temperature sensor."

FINISHED = "Your health check is finished. Thank you."

ALL_PHRASES = [
    GREETING,
    ASK_FINGER,
    FINGER_LOST,
    NO_FINGER_TIMEOUT,
    HEART_FINISHED,
    ASK_TEMPERATURE,
    FINISHED,
]


def start_health_check():
    play_sound("sounds/beep.wav")
    say(GREETING, "greeting.wav")


def ask_finger():
    say(ASK_FINGER, "ask_finger.wav")


def finger_lost():
    say(FINGER_LOST, "finger_lost.wav")


def no_finger_timeout():
    say(NO_FINGER_TIMEOUT, "no_finger_timeout.wav")


def heart_finished():
    say(HEART_FINISHED, "heart_finished.wav")


def ask_temperature():
    say(ASK_TEMPERATURE, "ask_temperature.wav")


def finished():
    say(FINISHED, "finished.wav")