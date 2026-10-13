"""
runtime/deployment_profile.py
Deployment profile I/O helpers.
Thin convenience layer over profile_storage.
"""
from runtime.profile_storage import ProfileStorage
from runtime.runtime_models import DeploymentProfile


def save_profile(candidate: dict, profile_id: str | None = None) -> str:
    """
    Saves a candidate dict as a DeploymentProfile JSON file.
    Returns the generated profile_id.
    """
    storage = ProfileStorage()
    return storage.save(candidate, profile_id=profile_id)


def load_all_profiles() -> list:
    """Returns all saved DeploymentProfile objects."""
    storage = ProfileStorage()
    return storage.load_all()


def delete_profile(profile_id: str) -> bool:
    """Deletes a profile by ID. Returns True on success."""
    storage = ProfileStorage()
    return storage.delete(profile_id)
