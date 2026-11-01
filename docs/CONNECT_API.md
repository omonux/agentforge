# AgentForge Connect API setup

Open **Connect API** in the AgentForge sidebar to add provider credentials. The page stores provider values in the backend encrypted vault, reports whether they are present, and offers provider-specific connection tests. Saved values are never returned to the browser.

## One-time encryption setup

Before saving a provider credential, configure `SECRET_ENCRYPTION_KEY` on the backend only.

Generate a Fernet key from the backend virtual environment:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the generated value as `SECRET_ENCRYPTION_KEY` in local `backend/.env` or the private hosting environment. Do not commit it. Back it up in a secure password manager: losing it makes encrypted credentials unrecoverable. Do not paste it into chat.

## Provider credentials shown in Connect API

| Service | Values to prepare | What the connection test does |
|---|---|---|
| AI Agent Provider | API key, base URL, model | Makes a minimal chat-completions request |
| Image AI Studio | Image API key, base URL, image model | Checks provider authentication without generating an image |
| AI Video Generation | Replicate API token, compatible `owner/model` slug | Checks Replicate account authentication |
| YouTube & Google OAuth | OAuth web-client ID, client secret, redirect URI, region | Checks credentials; the separate Connect channel button starts Google consent |
| Telegram Notifications | Bot token, private chat ID | Sends a test message |
| AI Voice Generation | ElevenLabs API key, permitted voice ID, optional model | Checks ElevenLabs account authentication |
| Payments | Paystack secret/public keys and plan codes; OPay merchant keys, merchant ID and sandbox URL | Paystack checks the account balance endpoint; OPay requires merchant-specific sandbox verification |
| Exchange Credentials | Binance/Bybit testnet keys and optional separate read-only live keys | Live order execution is not enabled by this credential page |

## YouTube setup

1. In Google Cloud Console, create an OAuth client of type **Web application**.
2. Enable YouTube Data API v3 and YouTube Analytics API for the project.
3. Add the exact redirect URI displayed for your deployed AgentForge backend, ending in `/api/v1/youtube/oauth/callback`.
4. Add the OAuth client ID, secret and redirect URI in Connect API.
5. Use **Test connection**, then **Connect channel**, and grant the requested scopes.
6. Reconnect an existing channel after the Analytics scopes are added. Revenue is only returned when the channel is eligible and Google grants the monetary analytics permission.

## Safety notes

- Never paste API keys into chat, source code, screenshots, browser storage or Git commits. Rotate any credential that has been exposed.
- Use test/sandbox credentials first. Paystack/OPay checkout remains disabled until `BILLING_ENABLED` is deliberately enabled in the server environment after sandbox verification.
- Keep trading credentials on testnet where possible. Live account credentials should be read-only, IP-restricted and have withdrawals disabled.
- YouTube uploads require explicit approval. If an upload response is ambiguous, AgentForge marks it `upload_unknown` and blocks automatic retries to reduce duplicate uploads.
- The workflow runner accepts only allowlisted agent-task, content-draft and Telegram-message actions. It does not execute arbitrary shell commands, SQL, URLs, payments, trades or automatic YouTube publishing.
