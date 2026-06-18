"""prompt 27: the ?function= safety layer — whitelists + column validation (no DB needed)."""
import pytest

from app.services.functions import (
    REGISTRY,
    FunctionError,
    _agg,
    _col,
    _date_col,
    _group_by,
    _measure,
    _parse_where,
)

ATTRS = {
    "region": {"data_type": "text"},
    "amount": {"data_type": "float"},
    "issue_date": {"data_type": "date"},
    "status": {"data_type": "text"},
}


def test_registry_has_the_five_primitives():
    assert set(REGISTRY) == {"aggregate", "timeseries", "top", "aging", "breakdown"}


def test_col_rejects_non_exposed_column():
    with pytest.raises(FunctionError) as exc:
        _col("salary", ATTRS, label="group_by")
    assert exc.value.status_code == 422


def test_col_rejects_injection_attempt():
    # not an exposed column -> 422 (and validate_identifier would also reject the non-snake_case)
    with pytest.raises(FunctionError):
        _col("region; drop table users", ATTRS, label="group_by")


def test_col_accepts_and_quotes_known_column():
    assert _col("region", ATTRS, label="group_by") == '"region"'


def test_agg_whitelist():
    assert _agg({"agg": "sum"}) == "sum"
    assert _agg({}) == "sum"  # default
    with pytest.raises(FunctionError):
        _agg({"agg": "delete"})


def test_measure_must_be_numeric():
    assert _measure({"measure": "amount"}, ATTRS) == '"amount"'
    with pytest.raises(FunctionError):
        _measure({"measure": "region"}, ATTRS)  # text is not a numeric measure


def test_date_col_must_be_a_date():
    assert _date_col({"date_col": "issue_date"}, ATTRS) == '"issue_date"'
    with pytest.raises(FunctionError):
        _date_col({"date_col": "region"}, ATTRS)


def test_group_by_required():
    with pytest.raises(FunctionError):
        _group_by({}, ATTRS)


def test_where_parses_to_bound_param():
    out: dict = {}
    clause = _parse_where("status!=paid", ATTRS, out)
    assert clause == '"status" <> :fn_w'
    assert out["fn_w"] == "paid"


def test_where_rejects_unknown_column():
    with pytest.raises(FunctionError):
        _parse_where("evil=1", ATTRS, {})
