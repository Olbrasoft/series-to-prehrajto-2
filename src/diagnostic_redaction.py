"""Remove request credentials before diagnostics enter durable state."""
import re


_PARAMETER = r"(?:key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|signature|sig|password|secret)"
_QUERY = re.compile(r"((?:[?&]|&amp;)" + _PARAMETER + r"=)[^&#\s'\"<>]+", re.I)
_ENCODED_QUERY = re.compile(
    r"((?:%3f|%26)" + _PARAMETER + r"%3d)(?:(?!%26|%23)[^\s'\"<>])+", re.I)
_USERINFO = re.compile(r"(https?://)[^/@\s]+:[^/@\s]+@", re.I)


def redact_text(value: str) -> str:
    value = _QUERY.sub(r"\1[REDACTED]", value)
    value = _ENCODED_QUERY.sub(r"\1[REDACTED]", value)
    return _USERINFO.sub(r"\1[REDACTED]@", value)


def redact_diagnostics(value):
    """Return a sanitized copy while preserving state structure and identity."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_diagnostics(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_diagnostics(item) for key, item in value.items()}
    return value
