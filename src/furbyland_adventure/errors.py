"""Failures a person can act on. These are printed without a traceback."""


class AdventureError(Exception):
    """Expected failure."""

    exit_code = 1


class ConfigError(AdventureError):
    """Missing or invalid configuration, premise, or state."""

    exit_code = 2


class UsernameMismatch(AdventureError):
    """The tokens belong to a different X account than ADVENTURE_USERNAME."""

    exit_code = 3


class XApiError(AdventureError):
    """The X API refused the call or could not be reached."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    exit_code = 4
