from voice import speak
from sound import play_sound

import time



def health_visit():


    play_sound("sounds/beep.wav")


    speak(
    "Hello. It is time for your daily health check."
    )


    time.sleep(3)   


    speak(
    "Please place your finger on the heart sensor "
    "and keep still."
    )


    # wait for MAX30102


    speak(
    "Your heart measurement is complete."
    )


    speak(
    "Please place your forehead near the temperature sensor."
    )


    # wait for MLX90614


    speak(
    "Your health check is finished. Thank you."
    )



health_visit()
