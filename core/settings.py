import os, json
from typing import Any, Dict, Literal


SettingType = Literal["number", "boolean", "text", "list"]

SETTINGS_SCHEMAS = {
    "user": {
        "preferred_leaderboard_output_type": {
            "type": "text", 
            "default": "image", 
            "choices": ["image", "text"], 
            "description": "Preferred output type for leaderboard commands"
        },
        "theme": {
            "type": "text", 
            "default": "light", 
            "choices": ["light", "dark", "purple"]
        },
    },
    "guild": {
        "guild_name": {"type": "text", "default": "",  "description": "Default guild name for commands like /guild and /coolness"},
        "guild_tag": {"type": "text", "default": "",  "description": "Default guild tag for commands like /guild and /coolness"},
    }
}

USER_FOLDER = "storages/user_settings"
GUILD_FOLDER = "storages/guild_settings"



class SettingsManager:
    def __init__(self, scope: Literal["user", "guild"], id: int):
        self.scope = scope
        self.id = str(id)
        self.schema = SETTINGS_SCHEMAS[scope]

        self.path = os.path.join(
            USER_FOLDER if scope == "user" else GUILD_FOLDER,
            f"{self.id}.json"
        )
        self._data = self._load_settings()


    def _load_settings(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {key: val["default"] for key, val in self.schema.items()}

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

        for key, val in self.schema.items():
            if key not in data:
                data[key] = val["default"]
        return data


    def _save_settings(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=4)


    def get(self, key: str) -> Any:
        if key not in self.schema:
            raise KeyError(f"Setting '{key}' does not exist.")
        return self._data.get(key, self.schema[key]["default"])


    def set(self, key: str, value: Any):
        if key not in self.schema:
            raise KeyError(f"Setting '{key}' does not exist.")
        
        schema = self.schema[key]
        expected_type = schema["type"]

        validated = self._validate_type(expected_type, value)
        if validated is None:
            raise ValueError(f"Value for '{key}' must be of type '{expected_type}'")

        if "choices" in schema and validated not in schema["choices"]:
            raise ValueError(f"Value for '{key}' must be one of: {schema['choices']}")

        self._data[key] = validated
        self._save_settings()


    def reset(self, key: str):
        if key not in self.schema:
            raise KeyError(f"Setting '{key}' does not exist.")
        self._data[key] = self.schema[key]["default"]
        self._save_settings()


    def all(self) -> Dict[str, Any]:
        return self._data.copy()


    def _validate_type(self, expected: SettingType, value: Any) -> Any:
        if expected == "number":
            try:
                return int(value)
            except Exception:
                return None
        if expected == "boolean":
            try:
                return bool(value)
            except Exception:
                return None
        if expected == "text":
            try:
                return str(value)
            except Exception:
                return None
        if expected == "list":
            try:
                return list(value)
            except Exception:
                return None
        return None
