# payments

Payments — processing, settlement, and payment schema storage.

## Domain Models

- payment.py

## Routes

- GET /payments/{payment_id}
- GET /jobs/{job_id}/payment
- POST /payments/{payment_id}/release
- POST /payments/{payment_id}/refund
- GET /payments/{payment_id}/receipt

## Services

- payments.py
