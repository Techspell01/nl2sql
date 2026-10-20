select
    i.order_id,
    i.item_seq,
    i.product_id,
    i.seller_id,
    o.order_status,
    o.purchased_at,
    cast(o.purchased_at as date) as order_date,
    i.price,
    i.freight_value
from staging.stg_order_items i
join staging.stg_orders o using (order_id)
