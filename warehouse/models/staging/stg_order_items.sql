select
    order_id,
    try_cast(order_item_id as integer) as item_seq,
    product_id,
    seller_id,
    try_cast(price as double)          as price,
    try_cast(freight_value as double)  as freight_value
from raw.order_items
