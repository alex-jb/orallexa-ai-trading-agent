"""Private operator gate for the legacy Streamlit prototype.

This gate is intentionally independent of the FastAPI and Next.js sessions.
It shares only the operator token so rotating that token revokes both UIs.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Mapping


SESSION_KEY = "_orallexa_legacy_owner_session"
SESSION_TTL_SECONDS = 15 * 60


def require_owner_session(st, environment: Mapping[str, str], *, now: float | None = None) -> None:
    """Stop Streamlit before any paid client or decision-log code can run."""
    if environment.get("ORALLEXA_ENABLE_LEGACY_STREAMLIT") != "1":
        st.error("The legacy Streamlit prototype is disabled. Use the Next.js dashboard.")
        st.stop()
        return

    owner_token = environment.get("ORALLEXA_UI_OWNER_TOKEN", "")
    if re.fullmatch(r"[0-9a-f]{64}", owner_token) is None:
        st.error("Legacy Streamlit requires a 64-character operator token.")
        st.stop()
        return

    current_time = time.time() if now is None else now
    fingerprint = hashlib.sha256(f"streamlit-v1:{owner_token}".encode()).hexdigest()
    session = st.session_state.get(SESSION_KEY)
    if isinstance(session, dict):
        previous = session.get("fingerprint")
        expiry = session.get("expires_at")
        if (isinstance(previous, str) and isinstance(expiry, (float, int))
                and hmac.compare_digest(previous, fingerprint)
                and current_time < expiry):
            return
    st.session_state.pop(SESSION_KEY, None)

    with st.form("legacy_owner_login", clear_on_submit=True):
        candidate = st.text_input("Operator token", type="password")
        submitted = st.form_submit_button("Unlock private prototype")

    if submitted and hmac.compare_digest(candidate, owner_token):
        st.session_state[SESSION_KEY] = {
            "fingerprint": fingerprint,
            "expires_at": current_time + SESSION_TTL_SECONDS,
        }
        return

    if submitted:
        st.error("Invalid operator token.")
    st.stop()
