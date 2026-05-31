import httpx
import logging
from datetime import datetime
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_order_message(order: dict, call_sid: str = "") -> str:
    items = order.get("items", [])
    items_lines = ""
    for item in items:
        qty = item.get("quantity", 1)
        name = item.get("product_name", "?")
        unit = item.get("unit_price", 0)
        items_lines += f"  • {qty}x {name} — {unit * qty} TND\n"

    delivery = order.get("delivery_type", "livraison")
    delivery_icon = "🚗" if delivery == "livraison" else "🏪"
    delivery_label = "Livraison à domicile" if delivery == "livraison" else "Sur place"

    address = order.get("address", "").strip()
    address_section = f"\n📍 *Adresse:*\n{address}" if address else ""

    ref = call_sid[-8:].upper() if call_sid else "N/A"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        f"📦 *Nouvelle Commande* — `{ref}`\n\n"
        f"👤 *Client:* {order.get('customer_name') or 'N/A'}\n"
        f"📞 *Téléphone:* {order.get('customer_phone') or 'N/A'}\n\n"
        f"🍽️ *Produits:*\n{items_lines}\n"
        f"💰 *Total:* {order.get('total', 0)} TND\n\n"
        f"{delivery_icon} *Mode:* {delivery_label}"
        f"{address_section}\n\n"
        f"🕒 *Heure:* {now}"
    )


async def send_to_telegram(chat_id: str, text: str) -> bool:
    url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            })
            if not resp.is_success:
                logger.error(f"Telegram error {resp.status_code}: {resp.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram request failed: {e}")
            return False


async def send_order_to_telegram(order: dict, call_sid: str = "") -> bool:
    message = format_order_message(order, call_sid)

    targets = [settings.TELEGRAM_CHAT_ID]
    if settings.TELEGRAM_ADMIN_CHAT_ID and settings.TELEGRAM_ADMIN_CHAT_ID != settings.TELEGRAM_CHAT_ID:
        targets.append(settings.TELEGRAM_ADMIN_CHAT_ID)

    results = []
    for chat_id in targets:
        ok = await send_to_telegram(chat_id, message)
        results.append(ok)

    return all(results)


async def send_admin_alert(text: str) -> bool:
    target = settings.TELEGRAM_ADMIN_CHAT_ID or settings.TELEGRAM_CHAT_ID
    return await send_to_telegram(target, f"⚠️ *Alerte Agent:*\n{text}")
