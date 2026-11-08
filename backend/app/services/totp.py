"""Double authentification (2FA) par codes temporaires (TOTP, RFC 6238) — compatible Google Authenticator,
Aegis, Bitwarden, 1Password, etc. Codes à 6 chiffres renouvelés toutes les 30 secondes.

Les codes de secours (à usage unique, en cas de perte du téléphone) ne sont stockés qu'en empreinte.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

ISSUER = "SynCiné"
DIGITS = 6
PERIOD = 30
RECOVERY_CODES = 10


def new_secret() -> str:
    """Secret aléatoire de 160 bits, en base32 (format attendu par les applications)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _counter_code(secret: str, counter: int, digits: int = DIGITS) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def code_at(secret: str, timestamp: float, digits: int = DIGITS) -> str:
    return _counter_code(secret, int(timestamp // PERIOD), digits)


def verify(secret: str, code: str, last_counter: int | None = None, now: float | None = None) -> int | None:
    """Vérifie un code (tolérance d'une période avant/après pour le décalage d'horloge).
    Renvoie le compteur accepté (à mémoriser pour refuser la réutilisation du même code), sinon None."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    current = int((now if now is not None else time.time()) // PERIOD)
    for counter in (current - 1, current, current + 1):
        if last_counter is not None and counter <= last_counter:
            continue  # code déjà utilisé (rejeu)
        if hmac.compare_digest(_counter_code(secret, counter), code):
            return counter
    return None


def provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={PERIOD}"


def qr_svg(uri: str) -> str:
    """QR code à scanner, en SVG (généré sur le serveur : le secret ne part chez aucun service tiers)."""
    import io

    import segno

    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", scale=5, border=2, dark="#000", light="#fff", xmldecl=False, svgns=True)
    return out.getvalue().decode()


# --- Codes de secours ----------------------------------------------------------------------


def new_recovery_codes() -> list[str]:
    """10 codes lisibles (xxxx-xxxx), à usage unique."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2)) for _ in range(RECOVERY_CODES)]


def _norm(code: str) -> str:
    return "".join(c for c in (code or "").lower() if c.isalnum())


def hash_recovery(code: str) -> str:
    return hashlib.sha256(_norm(code).encode()).hexdigest()


def use_recovery(code: str, hashes: list[str]) -> list[str] | None:
    """Si le code de secours est valide, renvoie la liste des empreintes restantes (code consommé), sinon None."""
    h = hash_recovery(code)
    for stored in hashes:
        if hmac.compare_digest(stored, h):
            return [x for x in hashes if x != stored]
    return None
