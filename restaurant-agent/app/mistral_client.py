from mistralai import Mistral
from .config import get_settings, load_menu
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)
settings = get_settings()
menu_data = load_menu()

SYSTEM_PROMPT_TEMPLATE = """Tu es un agent vocal IA pour le restaurant "{restaurant_name}".
Tu réponds en français. Tu peux comprendre l'arabe tunisien (darija) et répondre en français.

MENU DISPONIBLE:
{menu_text}

TON RÔLE:
1. Accueillir chaleureusement le client
2. Prendre la commande en identifiant les produits du menu
3. Demander les informations manquantes (livraison/sur place, adresse si livraison, nom, téléphone)
4. Calculer le total
5. Lire le résumé de la commande et demander confirmation
6. Remercier le client une fois confirmé

RÈGLES IMPORTANTES:
- Réponds TOUJOURS avec un JSON valide, rien d'autre
- Ne propose que des produits du menu
- Si un produit n'est pas au menu, dis poliment qu'il n'est pas disponible
- Pour la livraison, l'adresse est OBLIGATOIRE
- Demande le numéro de téléphone dans tous les cas
- Avant de terminer, lis TOUJOURS le résumé et attends que le client dise OUI ou confirme

FORMAT DE RÉPONSE (JSON strict):
{{
  "action": "continue" | "order_complete",
  "response_text": "texte à dire au client par téléphone",
  "order": {{
    "items": [
      {{"product_key": "pizza_margherita", "product_name": "Pizza Margherita", "quantity": 2, "unit_price": 12}}
    ],
    "delivery_type": "livraison" | "sur_place" | "",
    "customer_name": "",
    "customer_phone": "",
    "address": "",
    "total": 0
  }}
}}

- action "continue" : conversation en cours, pas encore confirmée par le client
- action "order_complete" : le client a dit OUI et confirmé la commande

EXEMPLES:
Client: "Je veux 2 pizzas margherita"
→ {{"action": "continue", "response_text": "Bien sûr, 2 Pizzas Margherita! C'est pour la livraison ou sur place?", "order": {{"items": [{{"product_key": "pizza_margherita", "product_name": "Pizza Margherita", "quantity": 2, "unit_price": 12}}], "delivery_type": "", "customer_name": "", "customer_phone": "", "address": "", "total": 24}}}}

Client: "Livraison" → demander l'adresse
Client: "Rue Bourguiba" → demander nom et téléphone
Client: "Ahmed, 98765432" → lire résumé et demander confirmation
Client: "Oui c'est bon" → {{"action": "order_complete", ...}}
"""


def build_menu_text() -> str:
    lines = []
    for key, item in menu_data.get("menu", {}).items():
        lines.append(f"  - {item['nom']} [{key}] : {item['prix']} TND — {item.get('description', '')}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    restaurant = menu_data.get("restaurant", {})
    return SYSTEM_PROMPT_TEMPLATE.format(
        restaurant_name=restaurant.get("nom", "Restaurant"),
        menu_text=build_menu_text()
    )


class MistralConversation:
    MAX_HISTORY = 30  # messages (15 turns)

    def __init__(self, call_sid: str):
        self.call_sid = call_sid
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt()
        self.current_order = {
            "items": [],
            "delivery_type": "",
            "customer_name": "",
            "customer_phone": "",
            "address": "",
            "total": 0.0
        }

    def get_greeting(self) -> str:
        restaurant = menu_data.get("restaurant", {})
        name = restaurant.get("nom", "notre restaurant")
        hours = restaurant.get("horaires", "")
        return (
            f"Bonjour et bienvenue chez {name}! "
            f"Je suis votre assistant vocal. "
            f"Comment puis-je vous aider? Que souhaitez-vous commander?"
        )

    async def process_message(self, user_input: str) -> dict:
        self.messages.append({"role": "user", "content": user_input})

        # Trim history to avoid token overflow
        if len(self.messages) > self.MAX_HISTORY:
            self.messages = self.messages[-self.MAX_HISTORY:]

        try:
            response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.messages
                ],
                response_format={"type": "json_object"},
                max_tokens=800,
                temperature=0.3
            )

            raw = response.choices[0].message.content
            self.messages.append({"role": "assistant", "content": raw})

            result = json.loads(raw)
            self._merge_order(result.get("order", {}))
            result["order"] = self.current_order
            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for call {self.call_sid}: {e}")
            return {
                "action": "continue",
                "response_text": "Désolé, pouvez-vous répéter votre commande s'il vous plaît?",
                "order": self.current_order
            }
        except Exception as e:
            logger.error(f"Mistral error for call {self.call_sid}: {e}")
            return {
                "action": "continue",
                "response_text": "Une erreur est survenue. Pouvez-vous répéter?",
                "order": self.current_order
            }

    def _merge_order(self, new_order: dict):
        if not new_order:
            return
        if new_order.get("items"):
            self.current_order["items"] = new_order["items"]
        for field in ("delivery_type", "customer_name", "customer_phone", "address"):
            val = new_order.get(field, "")
            if val:
                self.current_order[field] = val
        self._recalculate_total()

    def _recalculate_total(self):
        total = sum(
            item.get("unit_price", 0) * item.get("quantity", 1)
            for item in self.current_order["items"]
        )
        self.current_order["total"] = round(total, 3)


# In-memory session store for active calls
_sessions: dict[str, MistralConversation] = {}


def get_or_create_session(call_sid: str) -> MistralConversation:
    if call_sid not in _sessions:
        _sessions[call_sid] = MistralConversation(call_sid)
    return _sessions[call_sid]


def get_session(call_sid: str) -> Optional[MistralConversation]:
    return _sessions.get(call_sid)


def remove_session(call_sid: str):
    _sessions.pop(call_sid, None)
