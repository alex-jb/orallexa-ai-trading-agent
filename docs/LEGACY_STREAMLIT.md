# Private Streamlit prototype

`app_ui.py` is a legacy, private prototype. The supported owner interface is
the Next.js UI. Streamlit is disabled unless the operator explicitly sets
`ORALLEXA_ENABLE_LEGACY_STREAMLIT=1` and a separate random 64-character
`ORALLEXA_UI_OWNER_TOKEN` (the same token used by the Next.js owner sign-in).
Place these values in the ignored local `.env` or process environment, never
in source control. Generate the token with `openssl rand -hex 32`.

For an attended local session only:

```bash
streamlit run app_ui.py --server.address localhost
```

Enter the owner token in the password form. Streamlit loads the local `.env`
before the gate; the password form clears on submit, and the session stores
only a token fingerprint and expiry. The authenticated session expires after
15 minutes. Rotating the
owner token invalidates the existing session on its next rerun.

The older UI calls Anthropic and OpenAI directly and can write the decision
log. Those calls **do not share** the API's weekly LLM admission budget. Do
not deploy this prototype as a public or unattended service. Its token form
does not provide rate limiting, MFA, or the protections of a managed identity
gateway. Use the owner-gated Next.js UI and backend for maintained operations.
