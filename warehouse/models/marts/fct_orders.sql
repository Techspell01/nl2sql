with items as (
    select order_id, count(*) as item_count, sum(price) as items_value, sum(freight_value) as freight_value
    from staging.stg_order_items
    group by order_id
),
payments as (
    select
        order_id,
        sum(payment_value)                     as payment_value,
        arg_min(payment_type, payment_seq)     as primary_payment_type
    from staging.stg_payments
    group by order_id
),
reviews as (
    select order_id, avg(review_score) as avg_review_score
    from staging.stg_reviews
    group by order_id
)
select
    o.order_id,
    o.customer_id,
    o.order_status,
    o.purchased_at,
    cast(o.purchased_at as date)              as order_date,
    o.delivered_at,
    o.estimated_delivery_at,
    coalesce(i.item_count, 0)                 as item_count,
    coalesce(i.items_value, 0)                as items_value,
    coalesce(i.freight_value, 0)              as freight_value,
    p.payment_value,
    p.primary_payment_type,
    r.avg_review_score,
    date_diff('day', o.purchased_at, o.delivered_at) as delivery_days,
    case
        when o.delivered_at is null or o.estimated_delivery_at is null then null
        else o.delivered_at > o.estimated_delivery_at
    end                                       as is_late
from staging.stg_orders o
left join items i    using (order_id)
left join payments p using (order_id)
left join reviews r  using (order_id)
