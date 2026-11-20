from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CATEGORIES = ("STANDARD", "ZERO_RATED", "EXEMPT")
TWO_PLACES = Decimal("0.01")


class QuoteError(ValueError):
    """Raised when quote input is invalid."""


def money(value) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_quote(items, vat_rate, discount_percent=0):
    """
    Discount is applied first, then VAT is charged ONLY on STANDARD lines.
    Zero-rated and Exempt lines carry no tax.
    """
    if not items:
        raise QuoteError("A quote needs at least one item.")

    try:
        disc = Decimal(str(discount_percent or 0))
    except InvalidOperation:
        raise QuoteError("Discount must be a number.")
    if disc < 0 or disc > 100:
        raise QuoteError("Discount must be between 0 and 100.")

    rate_pct = Decimal(str(vat_rate))
    rate = rate_pct / 100

    summary = {c: {"net": Decimal("0.00"), "vat": Decimal("0.00")} for c in CATEGORIES}
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    total_vat = Decimal("0.00")
    result_items = []

    for n, it in enumerate(items, start=1):
        try:
            qty = Decimal(str(it["qty"]))
            price = Decimal(str(it["unit_price"]))
        except (InvalidOperation, KeyError):
            raise QuoteError(f"Line {n}: quantity and price must be numbers.")

        if qty <= 0 or price < 0:
            raise QuoteError(f"Line {n}: quantity must be above 0 and price cannot be negative.")

        category = it.get("tax_category")
        if category not in CATEGORIES:
            raise QuoteError(f"Line {n}: tax category must be one of {', '.join(CATEGORIES)}.")

        if not str(it.get("description", "")).strip():
            raise QuoteError(f"Line {n}: description is required.")

        net = money(qty * price)                    # before discount
        discount = money(net * disc / 100)
        taxable = net - discount
        vat = money(taxable * rate) if category == "STANDARD" else Decimal("0.00")

        result_items.append({
            "description": it["description"].strip(),
            "qty": qty,
            "unit_price": money(price),
            "tax_category": category,
            "line_net": net,
            "line_discount": discount,
            "line_vat": vat,
            "line_total": taxable + vat,
        })

        subtotal += net
        discount_total += discount
        total_vat += vat
        summary[category]["net"] += taxable
        summary[category]["vat"] += vat

    return {
        "items": result_items,
        "subtotal": subtotal,
        "discount_percent": disc,
        "discount_total": discount_total,
        "net_after_discount": subtotal - discount_total,
        "total_vat": total_vat,
        "grand_total": subtotal - discount_total + total_vat,
        "summary": summary,
        "vat_rate": rate_pct,
    }