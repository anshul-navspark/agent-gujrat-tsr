"""Utilities package.

Re-exports are resolved lazily (PEP 562). Importing this package used to pull in
`ai_column_detector`, and therefore **pandas**, for every caller — including the
scrape path, which has no use for it. That made pandas a hard dependency of
`gujtsr fetch` and broke a minimal skill-sandbox install with
`ModuleNotFoundError: No module named 'pandas'`.

The public names below are unchanged; they are just imported on first access.
"""

__all__ = [
    'setup_logging',
    'convert_survey_number',
    'sanitize_filename',
    'JSONTranslationSystem',
    'AIColumnDetector',
]

_EXPORTS = {
    'setup_logging': ('.logging_config', 'setup_logging'),
    'convert_survey_number': ('.survey_utils', 'convert_survey_number'),
    'sanitize_filename': ('.survey_utils', 'sanitize_filename'),
    'JSONTranslationSystem': ('.json_translations', 'JSONTranslationSystem'),
    # pandas-backed; only the Excel batch path needs it.
    'AIColumnDetector': ('.ai_column_detector', 'AIColumnDetector'),
}


def __getattr__(name):
    try:
        module, attr = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    from importlib import import_module
    value = getattr(import_module(module, __name__), attr)
    globals()[name] = value          # cache, so this runs once per name
    return value


def __dir__():
    return sorted(__all__)
