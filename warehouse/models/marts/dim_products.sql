select
    p.product_id,
    coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category,
    p.weight_g
from staging.stg_products p
left join staging.stg_category_translation t using (product_category_name)
