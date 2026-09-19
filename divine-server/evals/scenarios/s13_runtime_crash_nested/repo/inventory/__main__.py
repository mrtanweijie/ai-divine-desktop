from inventory.report import locations

RECORDS = [
    {"sku": "apple", "quantity": 12, "location": "A-01"},
    {"sku": "bolt", "quantity": 0, "location": "C-07"},
]

print("; ".join(locations(RECORDS)))
