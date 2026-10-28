"""Safe input loader (Requirements 2 and 3).

Turns an Input_File into ``list[RawRecord]`` or raises ``InputError``. Only the
standard ``json`` and ``csv`` parsers are used. Error checks follow the
Req 3.11 precedence; messages are one line and never contain file content.
"""
import csv
import io
import json
import os
from dataclasses import dataclass, field
from typing import Any

from dq_assistant.models import RECORD_FIELDS

MAX_INPUT_BYTES = 5 * 1024 * 1024  # 5,242,880 bytes, accepted at exactly this size

JSON_OBJECT = "json_object"
JSON_NON_OBJECT = "json_non_object"
CSV_ROW = "csv_row"

MSG_UNREADABLE = "Cannot read input file: {path}"
MSG_EXTENSION = "Unsupported format; use .json or .csv"
MSG_OVERSIZED = "Input exceeds the 5 MiB limit"
MSG_ENCODING = "Input must be UTF-8 encoded"
MSG_EMPTY = "Input file is empty"
MSG_BAD_JSON = "Input is not valid JSON"
MSG_NOT_LIST = "JSON must be a list of records"
MSG_CSV_HEADER = "CSV header is missing or unrecognized"
MSG_NO_RECORDS = "No records found in input"

_BOM = "\ufeff"
_WHITESPACE = " \t\r\n"
_ABSENT = object()


class InputError(Exception):
    """An input problem reported to the user as one line with exit code 2."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


@dataclass(frozen=True)
class RawRecord:
    """One input record, values kept exactly as read.

    ``fields`` maps field name to raw value (empty for non-object JSON
    elements). ``value`` holds the original element for ``json_non_object``.
    ``extra`` holds surplus CSV cells; ``ragged`` is True when there are any.
    """

    row_index: int
    fields: dict
    kind: str
    ragged: bool = False
    extra: tuple = ()
    value: Any = field(default=None, compare=False)


def _normalize_header(name: str) -> str:
    """Remove any BOM, strip surrounding whitespace, lower-case."""
    return name.replace(_BOM, "").strip().lower()


def load(path: str) -> list[RawRecord]:
    """Load ``path`` applying the Req 3.11 error precedence."""
    try:
        handle = open(path, "rb")
    except (OSError, ValueError, TypeError):
        raise InputError(MSG_UNREADABLE.format(path=path)) from None
    with handle:
        try:
            if not os.path.isfile(path):
                raise OSError
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".json", ".csv"):
                raise InputError(MSG_EXTENSION)
            if os.path.getsize(path) > MAX_INPUT_BYTES:
                raise InputError(MSG_OVERSIZED)
            data = handle.read(MAX_INPUT_BYTES + 1)
        except OSError:
            raise InputError(MSG_UNREADABLE.format(path=path)) from None
    if len(data) > MAX_INPUT_BYTES:  # file grew after the size check
        raise InputError(MSG_OVERSIZED)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InputError(MSG_ENCODING) from None
    if not text.strip(_WHITESPACE):
        raise InputError(MSG_EMPTY)
    records = _parse_json(text) if ext == ".json" else _parse_csv(text)
    if not records:
        raise InputError(MSG_NO_RECORDS)
    return records


def _parse_json(text: str) -> list[RawRecord]:
    try:
        top = json.loads(text)
    except (ValueError, RecursionError):
        raise InputError(MSG_BAD_JSON) from None
    if not isinstance(top, list):
        raise InputError(MSG_NOT_LIST)
    records = []
    for index, element in enumerate(top):
        if isinstance(element, dict):
            records.append(RawRecord(index, element, JSON_OBJECT))
        else:
            records.append(RawRecord(index, {}, JSON_NON_OBJECT, value=element))
    return records


def _parse_csv(text: str) -> list[RawRecord]:
    csv.field_size_limit(MAX_INPUT_BYTES)
    rows = (row for row in csv.reader(io.StringIO(text, newline="")) if row)
    try:
        header = next(rows, None)
        if header is None:
            raise InputError(MSG_CSV_HEADER)
        names = [_normalize_header(h) for h in header]
        if not any(n in RECORD_FIELDS for n in names):
            raise InputError(MSG_CSV_HEADER)
        records = []
        for index, row in enumerate(rows):
            values: dict = {}
            for i, name in enumerate(names):
                values[name] = row[i] if i < len(row) else _ABSENT  # last column wins
            fields = {k: v for k, v in values.items() if v is not _ABSENT}
            extra = tuple(row[len(names):])
            records.append(RawRecord(index, fields, CSV_ROW, bool(extra), extra))
    except csv.Error:
        raise InputError(MSG_CSV_HEADER) from None
    return records
