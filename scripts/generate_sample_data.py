"""Generate reproducible sample data with a March revenue dip and planted anomalies.

Run: python scripts/generate_sample_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUT = Path(__file__).resolve().parent.parent / "sample_data"
OUT.mkdir(exist_ok=True)

regions = ["North", "South", "East", "West"]
region_w = [0.22, 0.20, 0.30, 0.28]
products = {  # name: (category, unit_price, popularity)
    "Laptop (14-inch)": ("Electronics", 1200, 0.10), "Android phone (128 GB)": ("Electronics", 800, 0.16),
    "Wireless Earbuds": ("Accessories", 120, 0.20), "Office Chair": ("Furniture", 260, 0.12),
    "Height-adjustable desk": ("Furniture", 540, 0.07), "USB-C Dock": ("Accessories", 45, 0.18),
    "Smartwatch": ("Electronics", 300, 0.13), "LED Desk Lamp": ("Furniture", 35, 0.04),
}
first_names = ["Aisha", "Amelia", "Arjun", "Daniel", "Freya", "George", "Niamh", "Oliver", "Priya", "Sam"]
last_names = ["Bennett", "Clarke", "Hughes", "Khan", "Morgan", "Patel", "Shah", "Wright"]
customers = pd.DataFrame({
    "customer_id": [f"C{1000 + i}" for i in range(80)],
    "customer_name": [f"{first} {last}" for first in first_names for last in last_names],
    "segment": rng.choice(["Enterprise", "SMB", "Consumer"], 80, p=[0.2, 0.4, 0.4]),
    "country": rng.choice(["UK", "India", "Germany", "USA"], 80, p=[0.3, 0.25, 0.2, 0.25]),
    "signup_date": pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 700, 80), unit="D"),
})
weights = rng.pareto(1.6, 80) + 1
weights /= weights.sum()

rows = []
oid = 1
for month in range(1, 13):
    base = 130
    if month == 3:
        base = 70  # A deliberate March drop, concentrated in the East.
    n = int(base + rng.integers(-8, 9))
    for _ in range(n):
        region = rng.choice(regions, p=region_w)
        if month == 3 and region == "East" and rng.random() < 0.55:
            continue
        pname = rng.choice(list(products), p=np.array([v[2] for v in products.values()]) / sum(v[2] for v in products.values()))
        cat, price, _ = products[pname]
        qty = int(rng.integers(1, 6))
        disc = float(rng.choice([0, 0, 0, 0.05, 0.1, 0.15]))
        day = int(rng.integers(1, 28))
        rows.append({
            "order_id": f"ORD-{oid:05d}", "order_date": f"2024-{month:02d}-{day:02d}", "region": region,
            "product": pname, "category": cat, "customer_id": rng.choice(customers.customer_id, p=weights),
            "quantity": qty, "unit_price": price, "discount": disc,
            "revenue": round(qty * price * (1 - disc), 2),
        })
        oid += 1
sales = pd.DataFrame(rows)

# ---- planted anomalies (documented in README / used by tests) ----
extra = pd.DataFrame([
    {"order_id": "ORD-9001", "order_date": "2024-09-14", "region": "West", "product": "Laptop (14-inch)", "category": "Electronics",
     "customer_id": "C1003", "quantity": 40, "unit_price": 1200, "discount": 0.0, "revenue": 48000.0},   # bulk/typo
    {"order_id": "ORD-9002", "order_date": "2024-08-02", "region": "North", "product": "LED Desk Lamp", "category": "Furniture",
     "customer_id": "C1010", "quantity": 2, "unit_price": 35, "discount": 0.0, "revenue": -70.0},          # negative revenue
    {"order_id": "ORD-9003", "order_date": "2024-10-21", "region": "East", "product": "USB-C Dock", "category": "Accessories",
     "customer_id": "C1022", "quantity": 250, "unit_price": 45, "discount": 0.0, "revenue": 11250.0},      # suspicious quantity
    {"order_id": "ORD-9004", "order_date": "2024-11-09", "region": "South", "product": "Android phone (128 GB)", "category": "Electronics",
     "customer_id": "C1031", "quantity": 3, "unit_price": 800, "discount": 0.9, "revenue": 240.0},         # 90% discount
])
sales = pd.concat([sales, extra], ignore_index=True)
sales = sales.sample(frac=1, random_state=1).reset_index(drop=True)
# data-quality problems
sales.loc[rng.choice(len(sales), 12, replace=False), "region"] = None
sales = pd.concat([sales, sales.sample(6, random_state=3)], ignore_index=True)  # duplicates

sales.to_csv(OUT / "sales.csv", index=False)
customers.to_csv(OUT / "customers.csv", index=False)
print(f"sales.csv: {len(sales)} rows | customers.csv: {len(customers)} rows")
