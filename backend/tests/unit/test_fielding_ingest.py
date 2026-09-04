"""Unit tests for fielding-ingest parsing helpers."""
import numpy as np

from app.services.ingest.ingest_services import _pct_from_str


def test_pct_from_str_parses_savant_formats():
    assert _pct_from_str("85%") == 0.85
    assert _pct_from_str("-3%") == -0.03
    assert _pct_from_str("0%") == 0.0
    assert _pct_from_str(" 4% ") == 0.04


def test_pct_from_str_handles_missing_and_junk():
    assert _pct_from_str(None) is None
    assert _pct_from_str(np.nan) is None
    assert _pct_from_str("—") is None
    assert _pct_from_str("") is None
