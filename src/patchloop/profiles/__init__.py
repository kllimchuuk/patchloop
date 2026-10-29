from pathlib import Path

from patchloop.profiles.base import LanguageProfile, ProfileError, ProjectSetup
from patchloop.profiles.python import PythonProfile

PROFILES: list[LanguageProfile] = [PythonProfile()]


def detect_profile(project: Path) -> LanguageProfile:
    """The first profile that recognises the project; no fallback (CLAUDE.md)."""
    for profile in PROFILES:
        if profile.detect(project):
            return profile
    raise ProfileError(f"no language profile recognises {project} (supported: python)")


__all__ = [
    "PROFILES",
    "LanguageProfile",
    "ProfileError",
    "ProjectSetup",
    "PythonProfile",
    "detect_profile",
]
