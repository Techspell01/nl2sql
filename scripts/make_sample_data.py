"""Generate a small Olist-shaped sample so the project runs before the real data is downloaded.

The files match the real Olist file names and headers, so the same build script loads either.
The numbers are random; never report results computed on this sample.
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nl2sql import config  # noqa: E402

N_ORDERS = 3000
rng = random.Random(42)

STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "GO", "ES", "PE", "CE"]
STATE_WEIGHTS = [40, 13, 12, 6, 5, 4, 3, 2, 2, 2, 2, 1]
CITIES = {"SP": "sao paulo", "RJ": "rio de janeiro", "MG": "belo horizonte", "RS": "porto alegre",
          "PR": "curitiba", "SC": "florianopolis", "BA": "salvador", "DF": "brasilia",
          "GO": "goiania", "ES": "vitoria", "PE": "recife", "CE": "fortaleza"}
CATEGORIES = {"beleza_saude": "health_beauty", "relogios_presentes": "watches_gifts",
              "cama_mesa_banho": "bed_bath_table", "esporte_lazer": "sports_leisure",
              "informatica_acessorios": "computers_accessories", "moveis_decoracao": "furniture_decor",
              "utilidades_domesticas": "housewares", "brinquedos": "toys", "telefonia": "telephony",
              "automotivo": "auto"}
PAYMENT_TYPES = ["credit_card", "boleto", "voucher", "debit_card"]
STATUSES = ["delivered"] * 92 + ["shipped"] * 3 + ["canceled"] * 2 + ["unavailable", "invoiced", "processing"]
START, END = datetime(2016, 10, 1), datetime(2018, 8, 31)


def uid() -> str:
    return "%032x" % rng.getrandbits(128)


def ts(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S") if d else ""


def main() -> None:
    out = config.SAMPLE_DIR
    out.mkdir(parents=True, exist_ok=True)

    sellers = [{"seller_id": uid(), "seller_zip_code_prefix": str(rng.randint(10000, 99999)),
                "seller_city": CITIES[s], "seller_state": s}
               for s in rng.choices(STATES, STATE_WEIGHTS, k=120)]
    products = [{"product_id": uid(), "product_category_name": rng.choice(list(CATEGORIES)),
                 "product_name_lenght": rng.randint(20, 60), "product_description_lenght": rng.randint(100, 2000),
                 "product_photos_qty": rng.randint(1, 6), "product_weight_g": rng.randint(100, 15000),
                 "product_length_cm": rng.randint(10, 80), "product_height_cm": rng.randint(2, 60),
                 "product_width_cm": rng.randint(10, 60)} for _ in range(400)]
    price_of = {p["product_id"]: round(rng.lognormvariate(4.2, 0.8), 2) for p in products}

    customers, orders, items, payments, reviews = [], [], [], [], []
    span = (END - START).total_seconds()
    for _ in range(N_ORDERS):
        state = rng.choices(STATES, STATE_WEIGHTS)[0]
        customer = {"customer_id": uid(), "customer_unique_id": uid(),
                    "customer_zip_code_prefix": str(rng.randint(10000, 99999)),
                    "customer_city": CITIES[state], "customer_state": state}
        customers.append(customer)

        # skew volume toward later months, as in the real data
        bought = START + timedelta(seconds=span * rng.random() ** 0.7)
        status = rng.choice(STATUSES)
        estimated = (bought + timedelta(days=rng.randint(15, 35))).replace(hour=0, minute=0, second=0)
        delivered = bought + timedelta(days=rng.randint(3, 40)) if status == "delivered" else None
        order_id = uid()
        orders.append({"order_id": order_id, "customer_id": customer["customer_id"], "order_status": status,
                       "order_purchase_timestamp": ts(bought),
                       "order_approved_at": ts(bought + timedelta(hours=rng.randint(1, 30))),
                       "order_delivered_carrier_date": ts(bought + timedelta(days=2)) if delivered else "",
                       "order_delivered_customer_date": ts(delivered),
                       "order_estimated_delivery_date": ts(estimated)})

        total = 0.0
        for seq in range(1, rng.choice([1, 1, 1, 1, 2, 2, 3]) + 1):
            product = rng.choice(products)
            price, freight = price_of[product["product_id"]], round(rng.uniform(7, 45), 2)
            total += price + freight
            items.append({"order_id": order_id, "order_item_id": seq, "product_id": product["product_id"],
                          "seller_id": rng.choice(sellers)["seller_id"],
                          "shipping_limit_date": ts(bought + timedelta(days=6)),
                          "price": price, "freight_value": freight})
        payments.append({"order_id": order_id, "payment_sequential": 1,
                         "payment_type": rng.choices(PAYMENT_TYPES, [74, 19, 5, 2])[0],
                         "payment_installments": rng.randint(1, 10), "payment_value": round(total, 2)})
        if status == "delivered":
            late = delivered > estimated
            score = rng.choices([1, 2, 3, 4, 5], [30, 15, 20, 20, 15] if late else [8, 3, 8, 20, 61])[0]
            reviews.append({"review_id": uid(), "order_id": order_id, "review_score": score,
                            "review_comment_title": "", "review_comment_message": "",
                            "review_creation_date": ts(delivered + timedelta(days=1)),
                            "review_answer_timestamp": ts(delivered + timedelta(days=2))})

    tables = {
        "olist_customers_dataset.csv": customers, "olist_orders_dataset.csv": orders,
        "olist_order_items_dataset.csv": items, "olist_order_payments_dataset.csv": payments,
        "olist_order_reviews_dataset.csv": reviews, "olist_products_dataset.csv": products,
        "olist_sellers_dataset.csv": sellers,
        "product_category_name_translation.csv": [
            {"product_category_name": pt, "product_category_name_english": en} for pt, en in CATEGORIES.items()],
    }
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(out / name, index=False)
        print(f"  {name:<42} {len(rows):>6,} rows")
    print(f"Sample written to {out}")


if __name__ == "__main__":
    main()
