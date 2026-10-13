"""
runtime/profile_storage.py
JSON-based persistence for DeploymentProfile objects.
Saves profiles to runtime/profiles/ directory.
"""
import os
import json
import datetime
import uuid

from runtime.runtime_models import DeploymentProfile

PROFILES_DIR = os.path.join(os.path.dirname(__file__), "profiles")


class ProfileStorage:
    """
    Manages saving and loading of deployment profiles as JSON files.
    Each profile is stored as: runtime/profiles/<profile_id>.json
    """

    def __init__(self, profiles_dir: str | None = None):
        self.profiles_dir = profiles_dir or PROFILES_DIR
        os.makedirs(self.profiles_dir, exist_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, candidate: dict, profile_id: str | None = None) -> str:
        """
        Saves a candidate dict as a JSON profile file.
        Auto-generates profile_id if not provided.
        Returns the profile_id.
        """
        if not profile_id:
            ts_part = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            uid_part = str(uuid.uuid4())[:8]
            profile_id = f"profile_{ts_part}_{uid_part}"

        profile = DeploymentProfile.from_candidate(candidate, profile_id)
        file_path = self._path(profile_id)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)

        return profile_id

    def load(self, profile_id: str) -> DeploymentProfile | None:
        """Loads a single profile by ID. Returns None if not found."""
        file_path = self._path(profile_id)
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DeploymentProfile.from_dict(data)
        except Exception:
            return None

    def load_all(self) -> list:
        """Returns all DeploymentProfile objects from the profiles directory."""
        profiles = []
        try:
            for fname in sorted(os.listdir(self.profiles_dir), reverse=True):
                if fname.endswith(".json"):
                    profile_id = fname[:-5]
                    profile = self.load(profile_id)
                    if profile:
                        profiles.append(profile)
        except Exception:
            pass
        return profiles

    def delete(self, profile_id: str) -> bool:
        """Deletes a profile JSON file. Returns True on success."""
        file_path = self._path(profile_id)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception:
            pass
        return False

    def export_json(self, profile_id: str) -> str | None:
        """Returns the raw JSON string for a profile (for download buttons)."""
        file_path = self._path(profile_id)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_profile_ids(self) -> list:
        """Returns list of all saved profile IDs."""
        try:
            return [
                f[:-5] for f in sorted(os.listdir(self.profiles_dir), reverse=True)
                if f.endswith(".json")
            ]
        except Exception:
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _path(self, profile_id: str) -> str:
        return os.path.join(self.profiles_dir, f"{profile_id}.json")
