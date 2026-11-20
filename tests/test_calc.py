from decimal import Decimal
import pytest
from calc import calculate_quote, QuoteError

RATE = Decimal("16")

def item(cat, qty="1", price="100"):
    return {"description": "x", "qty": qty, "unit_price": price, "tax_category": cat}

def test_standard_is_taxed():
    r = calculate_quote([item("STANDARD")], RATE)
    assert r["total_vat"] == Decimal("16.00")
    assert r["grand_total"] == Decimal("116.00")

def test_zero_rated_and_exempt_carry_no_tax():
    r = calculate_quote([item("ZERO_RATED"), item("EXEMPT")], RATE)
    assert r["total_vat"] == Decimal("0.00")
    assert r["grand_total"] == Decimal("200.00")

def test_mixed_quote_taxes_only_standard():
    r = calculate_quote([item("STANDARD", "2", "50"), item("ZERO_RATED"), item("EXEMPT")], RATE)
    assert r["summary"]["STANDARD"]["vat"] == Decimal("16.00")
    assert r["summary"]["ZERO_RATED"]["vat"] == Decimal("0.00")
    assert r["subtotal"] == Decimal("300.00")
    assert r["grand_total"] == Decimal("316.00")

def test_invalid_category_rejected():
    with pytest.raises(QuoteError):
        calculate_quote([item("LUXURY")], RATE)

def test_empty_quote_rejected():
    with pytest.raises(QuoteError):
        calculate_quote([], RATE)
def test_discount_applied_before_vat():
    r = calculate_quote([item("STANDARD")], RATE, discount_percent=10)
    assert r["discount_total"] == Decimal("10.00")
    assert r["total_vat"] == Decimal("14.40")        # 16% of 90, not of 100
    assert r["grand_total"] == Decimal("104.40")

def test_discount_on_exempt_has_no_vat():
    r = calculate_quote([item("EXEMPT")], RATE, discount_percent=10)
    assert r["total_vat"] == Decimal("0.00")
    assert r["grand_total"] == Decimal("90.00")

def test_discount_over_100_rejected():
    with pytest.raises(QuoteError):
        calculate_quote([item("STANDARD")], RATE, discount_percent=150)        