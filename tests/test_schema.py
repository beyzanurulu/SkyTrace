from typing import Any

import pandas as pd
import pytest

from skytrace.parsers.schema import (
    TABLE_COLUMNS,
    TABLE_NAMES,
    FlightLog,
    LogMetadata,
    SchemaError,
    empty_table,
    time_index,
    validate_table,
)


def _empty_log(**overrides: pd.DataFrame) -> FlightLog:
    tables: dict[str, Any] = {name: empty_table(name) for name in TABLE_NAMES}
    tables.update(overrides)
    meta = LogMetadata(format="px4_ulog", source="x.ulg", duration_s=0.0)
    return FlightLog(metadata=meta, **tables)


def test_empty_tables_are_valid():
    log = _empty_log()
    assert log.motor_count == 0
    assert list(log.gps.columns) == list(TABLE_COLUMNS["gps"])


def test_motor_columns():
    assert list(empty_table("motors", 4).columns) == ["t", "m1", "m2", "m3", "m4"]
    validate_table("motors", pd.DataFrame({"t": [0.0], "m1": [0.5], "m2": [0.5]}))
    with pytest.raises(SchemaError):
        validate_table("motors", pd.DataFrame({"t": [0.0], "m2": [0.5]}))
    with pytest.raises(SchemaError):
        validate_table("motors", pd.DataFrame({"m1": [0.5]}))


def test_wrong_columns_rejected():
    with pytest.raises(SchemaError):
        _empty_log(battery=pd.DataFrame({"t": [0.0], "voltage": [12.0]}))


def test_time_must_be_float_and_sorted():
    bad_order = pd.DataFrame(
        {"t": [1.0, 0.5], "voltage": [1.0, 1.0], "current": [0.0, 0.0], "remaining": [1.0, 1.0]}
    )
    with pytest.raises(SchemaError, match="non-decreasing"):
        validate_table("battery", bad_order)
    int_time = bad_order.assign(t=[0, 1])
    with pytest.raises(SchemaError, match="float"):
        validate_table("battery", int_time)
    nan_time = bad_order.assign(t=[0.0, float("nan")])
    with pytest.raises(SchemaError, match="NaN"):
        validate_table("battery", nan_time)


def test_unknown_event_kind_rejected():
    events = pd.DataFrame({"t": [0.0], "kind": ["explosion"], "message": ["boom"]})
    with pytest.raises(SchemaError, match="unknown kinds"):
        validate_table("events", events)


def test_table_lookup():
    log = _empty_log()
    assert log.table("events") is log.events
    with pytest.raises(KeyError):
        log.table("metadata")


def test_from_file_dispatch(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        FlightLog.from_file(tmp_path / "flight.csv")


def test_time_index_keeps_subsecond_resolution():
    # pandas would infer second resolution for whole-number times and round 1.5 s windows.
    idx = time_index(pd.Series([0.0, 1.0, 2.0]))
    assert str(idx.dtype) == "timedelta64[ns]"
    s = pd.Series([1.0, 5.0, 2.0], index=idx)
    assert s.rolling(pd.Timedelta(seconds=1.5), min_periods=1).max().tolist() == [1.0, 5.0, 5.0]
    assert time_index(pd.Series([0.1234567]))[0] == pd.Timedelta(nanoseconds=123456700)
