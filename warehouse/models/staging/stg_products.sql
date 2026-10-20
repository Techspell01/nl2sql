select
    product_id,
    product_category_name,
    try_cast(product_weight_g as double) as weight_g
from raw.products
