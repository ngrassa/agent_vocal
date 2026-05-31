from .config import load_menu

menu_data = load_menu()


def enrich_items_from_menu(items: list) -> list:
    """Fill unit_price from menu.json if missing, add subtotal."""
    menu = menu_data.get("menu", {})
    enriched = []
    for item in items:
        key = item.get("product_key", "")
        menu_entry = menu.get(key, {})
        unit_price = item.get("unit_price") or menu_entry.get("prix", 0)
        quantity = item.get("quantity", 1)
        enriched.append({
            "product_key": key,
            "product_name": item.get("product_name") or menu_entry.get("nom", key),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": round(unit_price * quantity, 3)
        })
    return enriched


def calculate_total(items: list) -> float:
    return round(sum(i.get("unit_price", 0) * i.get("quantity", 1) for i in items), 3)


def finalize_order(order: dict) -> dict:
    """Enrich and recalculate before persisting."""
    order["items"] = enrich_items_from_menu(order.get("items", []))
    order["total"] = calculate_total(order["items"])
    return order


def validate_order(order: dict) -> tuple[bool, list[str]]:
    errors = []
    if not order.get("items"):
        errors.append("Aucun produit dans la commande")
    if not order.get("customer_phone"):
        errors.append("Numéro de téléphone manquant")
    if order.get("delivery_type") == "livraison" and not order.get("address"):
        errors.append("Adresse de livraison manquante")
    return len(errors) == 0, errors
