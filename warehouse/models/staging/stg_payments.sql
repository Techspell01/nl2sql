select
    order_id,
    try_cast(payment_sequential as integer)   as payment_seq,
    payment_type,
    try_cast(payment_installments as integer) as installments,
    try_cast(payment_value as double)         as payment_value
from raw.order_payments
