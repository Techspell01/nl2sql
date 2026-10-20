select
    review_id,
    order_id,
    try_cast(review_score as integer)           as review_score,
    try_cast(review_creation_date as timestamp) as reviewed_at
from raw.order_reviews
