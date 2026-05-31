import logging
from datetime import datetime
from twilio.twiml.voice_response import VoiceResponse, Gather
from sqlalchemy.orm import Session

from .mistral_client import get_or_create_session, remove_session
from .telegram_sender import send_order_to_telegram
from .order_parser import finalize_order
from .models import Order, OrderItem, CallSession
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Twilio voice settings — Polly.Léa is Amazon Polly French (fr-FR)
VOICE = "Polly.Lea"
LANGUAGE = "fr-FR"
GATHER_TIMEOUT = 8  # seconds of silence before fallback


def _twiml_gather(say_text: str, action_url: str) -> str:
    """Return TwiML: say text then listen for speech input."""
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        timeout=GATHER_TIMEOUT,
        language=LANGUAGE,
        speech_timeout="auto"
    )
    gather.say(say_text, voice=VOICE, language=LANGUAGE)
    response.append(gather)
    # Fallback when no speech detected after timeout
    response.say(
        "Je n'ai pas entendu votre réponse. Veuillez rappeler. Merci et à bientôt!",
        voice=VOICE,
        language=LANGUAGE
    )
    response.hangup()
    return str(response)


def _twiml_goodbye(say_text: str) -> str:
    """Return TwiML: say text then hang up."""
    response = VoiceResponse()
    response.say(say_text, voice=VOICE, language=LANGUAGE)
    response.hangup()
    return str(response)


async def handle_incoming_call(
    call_sid: str, from_number: str, gather_url: str, db: Session
) -> str:
    session = get_or_create_session(call_sid)

    db_call = db.query(CallSession).filter_by(call_sid=call_sid).first()
    if not db_call:
        db.add(CallSession(call_sid=call_sid, from_number=from_number, status="active"))
        db.commit()

    greeting = session.get_greeting()
    return _twiml_gather(greeting, gather_url)


async def handle_gather(
    call_sid: str, speech_result: str, gather_url: str, db: Session
) -> str:
    session = get_or_create_session(call_sid)

    if not speech_result or not speech_result.strip():
        return _twiml_gather(
            "Je n'ai pas compris. Pouvez-vous répéter?",
            gather_url
        )

    logger.info(f"[{call_sid}] Customer said: {speech_result!r}")

    result = await session.process_message(speech_result)
    response_text = result.get("response_text", "Pouvez-vous répéter?")
    action = result.get("action", "continue")

    # Update turn count
    db_call = db.query(CallSession).filter_by(call_sid=call_sid).first()
    if db_call:
        db_call.conversation_turns = (db_call.conversation_turns or 0) + 1
        db.commit()

    if action == "order_complete":
        order = finalize_order(result.get("order", session.current_order))
        logger.info(f"[{call_sid}] Order complete: {order}")

        # Persist order
        db_order = Order(
            call_sid=call_sid,
            customer_name=order.get("customer_name"),
            customer_phone=order.get("customer_phone"),
            delivery_type=order.get("delivery_type", "livraison"),
            address=order.get("address"),
            total=order.get("total", 0),
            status="confirmed"
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
                subtotal=item.get("subtotal", 0)
            ))

        db.commit()

        # Send to Telegram
        ok = await send_order_to_telegram(order, call_sid)
        if ok:
            db_order.telegram_sent = True
            db.commit()
        else:
            logger.warning(f"[{call_sid}] Telegram send failed")

        # Close session
        if db_call:
            db_call.status = "completed"
            db_call.ended_at = datetime.utcnow()
            db.commit()

        remove_session(call_sid)
        return _twiml_goodbye(response_text)

    return _twiml_gather(response_text, gather_url)


async def handle_call_status(call_sid: str, call_status: str, db: Session):
    if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
        db_call = db.query(CallSession).filter_by(call_sid=call_sid).first()
        if db_call and db_call.status == "active":
            db_call.status = call_status
            db_call.ended_at = datetime.utcnow()
            db.commit()
        remove_session(call_sid)
