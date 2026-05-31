import csv
import io
import logging
from datetime import datetime, date
from typing import Any

from fastapi import FastAPI, Request, Depends
from fastapi.responses import Response, HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .models import create_tables, get_db, Order, OrderItem, CallSession
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Restaurant AI Agent", version="1.0.0")


@app.on_event("startup")
async def startup():
    create_tables()
    logger.info("Restaurant AI Agent started (Asterisk mode)")


# ──────────────────────────────────────────
# Endpoint interne appelé par le script AGI
# ──────────────────────────────────────────

class OrderPayload(BaseModel):
    order: dict
    call_sid: str = ""
    caller_id: str = ""


@app.post("/api/internal/order")
async def internal_save_order(payload: OrderPayload, db: Session = Depends(get_db)):
    """Reçoit la commande depuis le script AGI Asterisk et la persiste."""
    order    = payload.order
    call_sid = payload.call_sid
    logger.info(f"[{call_sid}] Commande reçue depuis AGI: {order}")

    db_order = Order(
        call_sid=call_sid,
        customer_name=order.get("customer_name"),
        customer_phone=order.get("customer_phone"),
        delivery_type=order.get("delivery_type", "livraison"),
        address=order.get("address"),
        total=order.get("total", 0),
        status="confirmed",
        telegram_sent=True  # AGI envoie Telegram directement
    )
    db.add(db_order)
    db.flush()

    for item in order.get("items", []):
        db.add(OrderItem(
            order_id=db_order.id,
            product_key=item.get("product_key", ""),
            product_name=item.get("product_name", ""),
            quantity=item.get("quantity", 1),
            unit_price=item.get("unit_price", 0),
            subtotal=item.get("subtotal", item.get("unit_price", 0) * item.get("quantity", 1))
        ))

    db.commit()
    logger.info(f"[{call_sid}] Commande #{db_order.id} sauvegardée")
    return {"status": "ok", "order_id": db_order.id}


# ──────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(100).all()

    total_orders = db.query(Order).count()
    confirmed_count = db.query(Order).filter(Order.status == "confirmed").count()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(Order).filter(Order.created_at >= today_start).count()
    confirmed_orders = db.query(Order).filter(Order.status == "confirmed").all()
    total_revenue = sum(o.total for o in confirmed_orders)

    rows = ""
    for o in orders:
        badge = (
            '<span style="background:#27ae60;color:white;padding:2px 8px;border-radius:10px;font-size:.8em">Confirmée</span>'
            if o.status == "confirmed"
            else f'<span style="background:#e67e22;color:white;padding:2px 8px;border-radius:10px;font-size:.8em">{o.status}</span>'
        )
        tg = "✅" if o.telegram_sent else "❌"
        mode = "🚗 Livraison" if o.delivery_type == "livraison" else "🏪 Sur place"
        ts = o.created_at.strftime("%d/%m %H:%M") if o.created_at else "-"
        rows += f"""
        <tr>
            <td>#{o.id}</td>
            <td>{o.customer_name or "-"}</td>
            <td>{o.customer_phone or "-"}</td>
            <td>{mode}</td>
            <td><strong>{o.total} TND</strong></td>
            <td>{badge}</td>
            <td style="text-align:center">{tg}</td>
            <td>{ts}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restaurant AI Agent</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;background:#f0f2f5;color:#333}}
header{{background:#1a252f;color:#fff;padding:18px 24px;display:flex;align-items:center;gap:12px}}
header h1{{font-size:1.3em;font-weight:600}}
.stats{{display:flex;gap:16px;padding:20px;flex-wrap:wrap}}
.card{{background:#fff;border-radius:10px;padding:20px;flex:1;min-width:140px;box-shadow:0 1px 4px rgba(0,0,0,.1);text-align:center}}
.card .val{{font-size:2em;font-weight:700;color:#1a252f}}
.card .lbl{{color:#888;font-size:.85em;margin-top:4px}}
.actions{{padding:0 20px 16px;display:flex;gap:10px}}
.btn{{padding:9px 18px;background:#1a252f;color:#fff;border-radius:6px;text-decoration:none;font-size:.9em}}
.btn:hover{{background:#2c3e50}}
.orders{{padding:0 20px 30px}}
.orders h2{{margin-bottom:12px;color:#1a252f}}
table{{width:100%;background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.1);border-collapse:collapse;overflow:hidden}}
th{{background:#1a252f;color:#fff;padding:12px 14px;text-align:left;font-weight:500;font-size:.9em}}
td{{padding:11px 14px;border-bottom:1px solid #f0f0f0;font-size:.9em}}
tr:hover td{{background:#fafafa}}
tr:last-child td{{border-bottom:none}}
</style>
</head>
<body>
<header>
  <span style="font-size:1.8em">🍽️</span>
  <h1>Restaurant AI Agent — Dashboard</h1>
</header>
<div class="stats">
  <div class="card"><div class="val">{total_orders}</div><div class="lbl">Total commandes</div></div>
  <div class="card"><div class="val">{confirmed_count}</div><div class="lbl">Confirmées</div></div>
  <div class="card"><div class="val">{today_count}</div><div class="lbl">Aujourd'hui</div></div>
  <div class="card"><div class="val">{total_revenue:.0f} TND</div><div class="lbl">Chiffre d'affaires</div></div>
</div>
<div class="actions">
  <a class="btn" href="/export/csv">📥 Export CSV</a>
  <a class="btn" href="/api/orders">🔌 API JSON</a>
  <a class="btn" href="/health">❤️ Health</a>
</div>
<div class="orders">
  <h2>Dernières commandes</h2>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Client</th><th>Téléphone</th><th>Mode</th>
        <th>Total</th><th>Statut</th><th>Telegram</th><th>Heure</th>
      </tr>
    </thead>
    <tbody>{rows or "<tr><td colspan=8 style='text-align:center;padding:30px;color:#aaa'>Aucune commande pour l instant</td></tr>"}</tbody>
  </table>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


# ──────────────────────────────────────────
# REST API
# ──────────────────────────────────────────

@app.get("/api/orders")
async def api_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(200).all()
    result = []
    for o in orders:
        items = db.query(OrderItem).filter_by(order_id=o.id).all()
        result.append({
            "id": o.id,
            "call_sid": o.call_sid,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "delivery_type": o.delivery_type,
            "address": o.address,
            "total": o.total,
            "status": o.status,
            "telegram_sent": o.telegram_sent,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "items": [
                {"key": i.product_key, "name": i.product_name,
                 "qty": i.quantity, "unit_price": i.unit_price, "subtotal": i.subtotal}
                for i in items
            ]
        })
    return result


@app.get("/export/csv")
async def export_csv(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Client", "Téléphone", "Mode", "Adresse", "Total (TND)", "Statut", "Telegram", "Heure"])
    for o in orders:
        w.writerow([
            o.id, o.customer_name or "", o.customer_phone or "",
            o.delivery_type or "", o.address or "", o.total,
            o.status, "oui" if o.telegram_sent else "non",
            o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else ""
        ])
    buf.seek(0)
    filename = f"commandes_{date.today().isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat()}
