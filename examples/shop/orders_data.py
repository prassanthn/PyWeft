"""The shop's orders, shared by the pages that show them.

A plain module next to app.weft ships to the browser with the app, so any
page can `import orders_data`. A real app would fetch these from its server.
"""

ORDERS = [
    {"id": 1048, "customer": "Margaret Hamilton", "email": "margaret@apollo.dev",
     "date": "2026-11-02", "status": "pending", "items": 2, "total": 312.0},
    {"id": 1047, "customer": "Ada Lovelace", "email": "ada@engine.org",
     "date": "2026-11-01", "status": "paid", "items": 3, "total": 1250.0},
    {"id": 1046, "customer": "Grace Hopper", "email": "grace@cobol.net",
     "date": "2026-10-31", "status": "pending", "items": 1, "total": 89.9},
    {"id": 1045, "customer": "Alan Turing", "email": "alan@bletchley.uk",
     "date": "2026-10-30", "status": "paid", "items": 2, "total": 410.0},
    {"id": 1044, "customer": "Katherine Johnson", "email": "katherine@orbit.space",
     "date": "2026-10-29", "status": "refunded", "items": 1, "total": 72.5},
    {"id": 1043, "customer": "Dennis Ritchie", "email": "dmr@bell-labs.com",
     "date": "2026-10-27", "status": "paid", "items": 4, "total": 538.4},
    {"id": 1042, "customer": "Barbara Liskov", "email": "barbara@clu.edu",
     "date": "2026-10-26", "status": "paid", "items": 1, "total": 145.0},
    {"id": 1041, "customer": "Edsger Dijkstra", "email": "ewd@goto.nl",
     "date": "2026-10-24", "status": "refunded", "items": 2, "total": 260.0},
]

STATUSES = ["paid", "pending", "refunded"]


def find(order_id):
    """The order with this id, or None."""
    return next((order for order in ORDERS if order["id"] == order_id), None)


def money(amount):
    """1250.0 -> "$1,250.00" """
    return f"${amount:,.2f}"


def initials(name):
    """"Ada Lovelace" -> "AL", for the round avatars."""
    return "".join(part[0] for part in name.split()[:2]).upper()


def nice_date(iso):
    """"2026-11-02" -> "Nov 2, 2026" """
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{months[month - 1]} {day}, {year}"
