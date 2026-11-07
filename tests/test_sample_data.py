from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def test_sample_customers_are_named_and_synthetic():
    customers = pd.read_csv(ROOT / "sample_data" / "customers.csv")

    assert len(customers) == 80
    assert customers["customer_id"].is_unique
    assert customers["customer_name"].str.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+").all()
    assert not customers["customer_name"].str.startswith("Customer ").any()


def test_sample_orders_keep_planted_anomalies_descriptive():
    sales = pd.read_csv(ROOT / "sample_data" / "sales.csv").set_index("order_id")

    assert sales.loc["ORD-9001", "product"] == "Laptop (14-inch)"
    assert sales.loc["ORD-9002", "revenue"] == -70
    assert sales.loc["ORD-9003", "quantity"] == 250
    assert sales.loc["ORD-9004", "discount"] == 0.9
