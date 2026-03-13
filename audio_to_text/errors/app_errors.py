class AppError(Exception):
    """Base application error."""


class ConfigurationError(AppError):
    """Settings or application configuration error."""


class EnvironmentError(AppError):
    """Environment readiness error."""


class InputValidationError(AppError):
    """User input validation error."""


class DownloadError(AppError):
    """Download-specific error."""


class TranscriptionError(AppError):
    """Transcription backend error."""


class OutputError(AppError):
    """Output writing error."""
