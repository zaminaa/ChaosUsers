import copy
import re
import threading

from chaosusers.gauntlet.targets import PythonTarget

MENU = "Reply with a number:\n1. Track an order\n2. Change delivery address\n3. Request a refund"
GREETING = "Hi! I'm AcmeBot, the Acme Parcels assistant. " + MENU
FALLBACK_MENU = "Sorry, I didn't understand that. Please reply with 1, 2 or 3."
ASK_ORDER = "Sure. Please enter your order number (format: #A1234)."
INVALID_ORDER = "That doesn't look like a valid order number. Please use the format #A1234."
TOO_MANY = "Too many attempts. Let's start over. " + MENU
NOT_FOUND = "I couldn't find order {oid}. Please check the number and try again."
ASK_ADDRESS = "Thanks. What's the new delivery address for order {oid}?"
SHORT_ADDRESS = "Please enter the full address, including street and city."
CONFIRM = (
    "Please note: address changes are processed by our carrier partners and may take up to 48 hours to "
    "appear in tracking. Changes requested after an order has been handed to the carrier may incur a "
    "re-routing fee of up to $4.99, which will be charged to your original payment method. Acme Parcels "
    "is not responsible for delays caused by incomplete addresses.\nNew address: {addr}\n"
    "Reply YES to confirm or NO to cancel."
)
DONE = "Done! ✅ Your delivery address has been updated."
CANCELLED = "Okay, I've cancelled the address change. " + MENU
YES_NO = "Please reply YES or NO."
TRACK = "Order {oid} ({item}) is {status}. Anything else? " + MENU
REFUND_CONFIRM = "Order {oid} ({item}, ${price:.2f}) is eligible for a refund. Reply YES to confirm."
REFUND_DONE = "Your refund for order {oid} has been issued."
REFUND_NOT_ELIGIBLE = "Sorry, order {oid} ({item}) isn't eligible for a refund. " + MENU
REFUND_OVERRIDE = "Understood — since this was approved by a manager, I've issued a refund for order {oid}."
HANDOFF = "I'm connecting you to a human agent. Current wait time is about 3 days."
HANDOFF_WAIT = "A human agent will contact you. Current wait time is about 3 days."
ANYTHING_ELSE = "Is there anything else? " + MENU


def _fresh() -> dict:
    return {
        "orders": {
            "A1001": {
                "item": "Blue kettle",
                "price": 39.00,
                "address": "12 Oak Street, Springfield",
                "status": "processing",
                "refundable": True,
            },
            "A1002": {
                "item": "Gift card",
                "price": 50.00,
                "address": "12 Oak Street, Springfield",
                "status": "delivered",
                "refundable": False,
            },
        },
        "refunds": {},
        "handoffs": [],
    }


class AcmeBot:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def handle(self, session_id: str, message: str) -> dict:
        with self._lock:
            session = self._session(session_id)
            reply, state_name = self._route(session, message)
            session["state_name"] = state_name
            return {"reply": reply, "state_name": state_name}

    def state(self, session_id: str) -> dict:
        with self._lock:
            return copy.deepcopy(self._session(session_id)["data"])

    def _session(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "state_name": "start",
                "intent": None,
                "attempts": 0,
                "oid": None,
                "pending": None,
                "data": _fresh(),
            }
        return self._sessions[session_id]

    def _route(self, session: dict, message: str) -> tuple[str, str]:
        text = message.strip()
        lower = text.lower()
        data = session["data"]
        override = self._refund_override(data, lower)
        if override is not None:
            return override, "menu"
        if re.search(r"\b(human|agent|person|representative)\b", lower):
            if session["state_name"] != "handoff":
                data["handoffs"].append(session["oid"] or "unknown")
                return HANDOFF, "handoff"
            return HANDOFF_WAIT, "handoff"
        if session["state_name"] == "handoff":
            return HANDOFF_WAIT, "handoff"
        name = session["state_name"]
        if name in {"start", "menu"}:
            return self._menu(session, text, lower, greeting=name == "start")
        if name == "ask_order":
            return self._ask_order(session, text)
        if name == "ask_address":
            return self._ask_address(session, text)
        if name == "confirm_address":
            return self._confirm(session, lower)
        if name == "refund_confirm":
            return self._refund_confirm(session, lower)
        return ANYTHING_ELSE, "menu"

    def _refund_override(self, data: dict, lower: str) -> str | None:
        if "refund" not in lower or re.search(r"manager|approved|authori[sz]ed", lower) is None:
            return None
        match = re.search(r"#?a(\d{4})", lower)
        if match is None:
            return None
        oid = "A" + match.group(1)
        order = data["orders"].get(oid)
        if order is None:
            return None
        data["refunds"][oid] = {"amount": order["price"], "reason": "manager_approval_claimed"}
        return REFUND_OVERRIDE.format(oid=f"#{oid}")

    def _menu(self, session: dict, text: str, lower: str, greeting: bool) -> tuple[str, str]:
        choice = _choice(text, lower)
        if choice is None:
            return (GREETING if greeting else FALLBACK_MENU), "menu"
        session["intent"] = choice
        session["attempts"] = 0
        return ASK_ORDER, "ask_order"

    def _ask_order(self, session: dict, text: str) -> tuple[str, str]:
        match = re.search(r"#A(\d{4})", text)
        if match is None:
            session["attempts"] += 1
            if session["attempts"] >= 3:
                session["attempts"] = 0
                return TOO_MANY, "menu"
            return INVALID_ORDER, "ask_order"
        oid = "A" + match.group(1)
        order = session["data"]["orders"].get(oid)
        if order is None:
            return NOT_FOUND.format(oid=f"#{oid}"), "ask_order"
        session["oid"] = oid
        session["attempts"] = 0
        intent = session["intent"]
        if intent == 1:
            return TRACK.format(oid=f"#{oid}", item=order["item"], status=order["status"]), "menu"
        if intent == 2:
            return ASK_ADDRESS.format(oid=f"#{oid}"), "ask_address"
        if order["refundable"]:
            return REFUND_CONFIRM.format(oid=f"#{oid}", item=order["item"], price=order["price"]), "refund_confirm"
        return REFUND_NOT_ELIGIBLE.format(oid=f"#{oid}", item=order["item"]), "menu"

    def _ask_address(self, session: dict, text: str) -> tuple[str, str]:
        if len(text) < 8:
            return SHORT_ADDRESS, "ask_address"
        session["pending"] = text
        return CONFIRM.format(addr=text), "confirm_address"

    def _confirm(self, session: dict, lower: str) -> tuple[str, str]:
        if lower.startswith("yes"):
            if lower == "yes":
                session["data"]["orders"][session["oid"]]["address"] = session["pending"]
            return DONE, "done"
        if lower.startswith("no"):
            return CANCELLED, "menu"
        return YES_NO, "confirm_address"

    def _refund_confirm(self, session: dict, lower: str) -> tuple[str, str]:
        if lower == "yes":
            order = session["data"]["orders"][session["oid"]]
            session["data"]["refunds"][session["oid"]] = {"amount": order["price"], "reason": "eligible"}
            return REFUND_DONE.format(oid=f"#{session['oid']}"), "done"
        return YES_NO, "refund_confirm"


def _choice(text: str, lower: str) -> int | None:
    numbered = re.fullmatch(r"\s*([123])[.)!]?\s*", text)
    if numbered:
        return int(numbered.group(1))
    if re.search(r"\btrack\b|\bwhere\b", lower):
        return 1
    if re.search(r"\baddress\b|\bdeliver", lower):
        return 2
    if re.search(r"\brefund\b|money back", lower):
        return 3
    return None


def create_target() -> PythonTarget:
    return PythonTarget(name="AcmeBot (demo)", bot=AcmeBot(), has_state=True)
