import pygame

pygame.mixer.init()

def play_sound(file):
    pygame.mixer.music.load(file)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pass


