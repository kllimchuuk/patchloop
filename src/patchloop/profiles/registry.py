"""Registered language profiles and detection of the one that fits a project."""

from pathlib import Path

from patchloop.profiles.base import LanguageProfile, ProfileError
from patchloop.profiles.python import PythonProfile

PROFILES: list[LanguageProfile] = [PythonProfile()]


def detect_profile(project: Path) -> LanguageProfile:
    """The first profile that recognises the project; no fallback (CLAUDE.md)."""
    for profile in PROFILES:
        if profile.detect(project):
            return profile
    raise ProfileError(f"no language profile recognises {project} (supported: python)")
