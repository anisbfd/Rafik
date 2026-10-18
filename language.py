import json
import os

SETTINGS_FILE = "settings.json"


def load():

    if os.path.exists(SETTINGS_FILE):

        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)

    data = {
        "language": "en"
    }

    save(data)

    return data


def save(data):

    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_language():

    return load()["language"]


def set_language(language):

    data = load()

    data["language"] = language

    save(data)