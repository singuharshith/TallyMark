from core.anomalies import detect_anomalies


def test_planted_anomalies_found_with_reasons(sales):
    rep = detect_anomalies(sales, "sales")
    flagged = set(rep.rows["order_id"])
    assert {"ORD-9001", "ORD-9002", "ORD-9003", "ORD-9004"} <= flagged
    top = rep.rows.iloc[0]
    assert "σ" in top["why_flagged"] and top["severity"] > 5
    neg = rep.rows[rep.rows["order_id"] == "ORD-9002"].iloc[0]
    assert "negative" in neg["why_flagged"]


def test_clean_data_flags_little(customers):
    assert detect_anomalies(customers, "customers").n_flagged == 0


def test_flagged_count_is_not_limited_by_display_rows(sales):
    complete = detect_anomalies(sales, "sales", max_rows=1000)
    limited = detect_anomalies(sales, "sales", max_rows=1)

    assert len(limited.rows) == 1
    assert limited.n_flagged == complete.n_flagged
    assert limited.n_flagged > 1
