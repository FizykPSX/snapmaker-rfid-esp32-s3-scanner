import json

class Config:
    def __init__(self, path="config.json"):
        with open(path, "r") as f:
            self._cfg = json.load(f)

    def lcd(self):
        return self._cfg["lcd"]

    def rfid(self):
        return self._cfg["rfid"]

    def printer(self):
        return self._cfg["printer"]

    def button(self):
        return self._cfg["button"]

    def ui(self):
        return self._cfg["ui"]

    def spoolman(self):
        return self._cfg.get("spoolman", {"enabled": False})
