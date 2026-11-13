"""Typed errors, so the backend can tell the user what went wrong in plain words.

AltInfoError       base class; `code` is stable for the frontend, `message` is shown to the user
InvalidQuery       the text typed is not a plausible ticker or commodity name
UnknownAsset       nothing found for the query on any source
SourceUnavailable  one source could not be reached (the analysis continues without it)
NoData             the asset exists but there is not enough data to analyse it
"""


class AltInfoError(Exception):
    code, status = "error", 500

    def __init__(self, message, detail=None):
        super().__init__(message)
        self.message, self.detail = message, detail

    def to_dict(self):
        return {"code": self.code, "message": self.message, "detail": self.detail}


class InvalidQuery(AltInfoError):
    code, status = "invalid_query", 400


class UnknownAsset(AltInfoError):
    code, status = "unknown_asset", 404


class SourceUnavailable(AltInfoError):
    code, status = "source_unavailable", 503


class NoData(AltInfoError):
    code, status = "no_data", 422
