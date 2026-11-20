"""Sign in with Google (OAuth 2.0 authorization code flow + PKCE).

Google only returns people to redirect addresses registered in advance, but the online link changes every
time the launcher goes online. So there are two registered addresses:
  * http://localhost:<port>/auth/google/callback      - used on the team laptop itself
  * https://kieran-snack.github.io/scout/auth.html     - a relay page for everyone using the online link; it
    reads which tunnel the sign-in started from (inside `state`) and forwards the browser there.
The authorization code is useless without the client secret, which only SnackScout's server has, and the
signed `state` + PKCE verifier stored in the person's session stop anyone else from finishing their sign-in.
"""
import base64
import hashlib
import json
import re
import secrets
import urllib.parse

import requests
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import db
from .config import PORT

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
RELAY_URL = "https://kieran-snack.github.io/scout/auth.html"
LOCAL_ORIGIN = f"http://localhost:{PORT}"
LOCAL_REDIRECT = f"{LOCAL_ORIGIN}/auth/google/callback"
TUNNEL_ORIGIN_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def client():
    """(client_id, client_secret) shared with every laptop through the team cloud."""
    return db.team_config("google_client_id") or "", db.team_config("google_client_secret") or ""


def configured():
    cid, secret = client()
    return bool(cid and secret)


def origin_for(request):
    """Where this browser is using SnackScout from, if Google sign-in can work there."""
    host = (request.host or "").lower()
    if request.headers.get("Cf-Connecting-Ip") and host.endswith(".trycloudflare.com"):
        origin = "https://" + host
        return origin if TUNNEL_ORIGIN_RE.fullmatch(origin) else None
    if host in (f"localhost:{PORT}", f"127.0.0.1:{PORT}"):
        return LOCAL_ORIGIN
    return None  # e.g. http://10.x.x.x:5000 on Wi-Fi: Google won't redirect to private addresses


def redirect_uri_for(origin):
    return LOCAL_REDIRECT if origin == LOCAL_ORIGIN else RELAY_URL


def _signer(secret_key):
    return URLSafeTimedSerializer(secret_key, salt="snackscout-google")


def start(secret_key, origin, mode, session):
    """Build Google's sign-in URL. mode: 'login' or 'link'."""
    nonce, verifier = secrets.token_urlsafe(16), secrets.token_urlsafe(48)
    session["g_nonce"], session["g_verifier"] = nonce, verifier
    signed = _signer(secret_key).dumps({"n": nonce, "o": origin, "m": mode})
    # The relay page needs the origin before it can verify anything, so it's also carried in plain form.
    state = base64.urlsafe_b64encode(origin.encode()).decode().rstrip("=") + "~" + signed
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    cid, _ = client()
    params = dict(client_id=cid, redirect_uri=redirect_uri_for(origin), response_type="code",
                  scope="openid email profile", state=state, code_challenge=challenge,
                  code_challenge_method="S256", prompt="select_account")
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


class GoogleError(Exception):
    pass


def finish(secret_key, origin, args, session):
    """Check the state, swap the code for Google's ID token, and return the verified identity."""
    if args.get("error"):
        raise GoogleError("Google sign-in was cancelled." if args["error"] == "access_denied"
                          else f"Google said: {args['error']}")
    state, code = args.get("state", ""), args.get("code", "")
    try:
        data = _signer(secret_key).loads(state.split("~", 1)[-1], max_age=600)
    except SignatureExpired:
        raise GoogleError("That sign-in took too long. Try again.")
    except BadSignature:
        raise GoogleError("That sign-in link isn't valid. Try again.")
    nonce, verifier = session.pop("g_nonce", None), session.pop("g_verifier", None)
    if not nonce or data.get("n") != nonce or data.get("o") != origin or not verifier:
        raise GoogleError("This sign-in was started in a different browser or tab. Try again here.")
    cid, csecret = client()
    r = requests.post(TOKEN_URL, timeout=15, data=dict(
        code=code, client_id=cid, client_secret=csecret, redirect_uri=redirect_uri_for(origin),
        grant_type="authorization_code", code_verifier=verifier))
    if r.status_code != 200:
        raise GoogleError(f"Google didn't accept the sign-in ({r.json().get('error', r.status_code)}).")
    id_token = r.json().get("id_token")
    info = requests.get(TOKENINFO_URL, params={"id_token": id_token}, timeout=15).json()
    if info.get("aud") != cid or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleError("Google's answer wasn't meant for SnackScout.")
    if str(info.get("email_verified")).lower() != "true":
        raise GoogleError("That Google account's email isn't verified.")
    return {"sub": info["sub"], "email": info.get("email"), "name": info.get("name") or info.get("email"),
            "mode": data.get("m", "login")}
