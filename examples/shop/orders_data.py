"""The shop's orders, shared by the pages that show them.

A plain module next to app.weft ships to the browser with the app, so any
page can `import orders_data`. A real app would fetch these from its server.
"""

ORDERS = [
    {"id": 1041, "customer": "Ada Lovelace", "status": "paid", "items": 3, "total": 1250.0},
    {"id": 1042, "customer": "Grace Hopper", "status": "pending", "items": 1, "total": 89.9},
    {"id": 1043, "customer": "Alan Turing", "status": "paid", "items": 2, "total": 410.0},
    {"id": 1044, "customer": "Katherine Johnson", "status": "refunded", "items": 1, "total": 72.5},
]


def find(order_id):
    """The order with this id, or None."""
    return next((order for order in ORDERS if order["id"] == order_id), None)
