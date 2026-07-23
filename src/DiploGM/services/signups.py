import json
from dataclasses import asdict
from pathlib import Path

from DiploGM.models.signup import PlayerSignup
from DiploGM.services.base import BaseService

SIGNUP_FILE = Path("assets/signups.json")
_default_contents = {
    "metadata": {
        "wave": "",
        "accepting_responses": False
    }
}

_reserved_keys = ["metadata"]

class SignupService(BaseService):
    def __init__(self) -> None:
        if not SIGNUP_FILE.exists():
            SIGNUP_FILE.touch()
            SIGNUP_FILE.write_text(
                json.dumps(_default_contents)
            )

        with open(SIGNUP_FILE) as f:
            self.data = json.load(f)

    def _save(self):
        SIGNUP_FILE.unlink(missing_ok=True)

        SIGNUP_FILE.touch()
        SIGNUP_FILE.write_text(
            json.dumps(self.data, indent=4)
        )

    def define_wave(self, name: str):
        if name in _reserved_keys:
            raise ValueError(f"'{name}' is a reserved keyword")

        self.data["metadata"]["wave"] = name
        self.data[name] = self.data.get(name, {})
        self._save()

    def clear_wave(self, name: str):
        if name in _reserved_keys:
            raise ValueError(f"'{name}' is a reserved keyword")

        self.data[name] = {}
        self._save()

    def open_wave(self):
        self.data["metadata"]["accepting_responses"] = True
        self._save()
    
    def close_wave(self):
        self.data["metadata"]["accepting_responses"] = False
        self._save()

    def record_signup(self, name: str, signup: PlayerSignup):
        if not self.data["metadata"]["accepting_responses"]:
            raise RuntimeError("Not accepting responses currently.")

        wave_name = self.data["metadata"]["wave"]

        wave = self.data.get(wave_name, {})
        wave[name] = asdict(signup)

        self.data[wave_name] = wave
        self._save()

    def delete_signup(self, name: str):
        wave_name = self.data["metadata"]["wave"]
        wave = self.data.get(wave_name, {})

        if name in wave:
            del wave[name]

        self.data[wave_name] = wave
        self._save()

signup_service = SignupService()
