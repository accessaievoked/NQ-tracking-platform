"""Diagnose the Anthropic (Claude) connection — one minimal call, fail fast.

Tells you exactly why the AI report hangs/fails: bad key, no credit, wrong model,
or blocked network. Run:

    python -m scripts.check_anthropic
"""
from __future__ import annotations

import time

from app.config import settings


def main() -> None:
    key = settings.anthropic_api_key or ""
    print(f"ANTHROPIC_API_KEY set: {bool(key)}  (length {len(key)}, starts with {key[:7]!r})")
    print(f"ANTHROPIC_MODEL: {settings.anthropic_model}")
    if not key:
        print("\nNo key loaded. Put ANTHROPIC_API_KEY=sk-ant-... in your .env, then retry.")
        return

    try:
        import anthropic
    except ModuleNotFoundError:
        print("\n'anthropic' package not installed. Run: pip install anthropic")
        return

    # max_retries=0 + short timeout => it errors immediately instead of hanging.
    client = anthropic.Anthropic(api_key=key, timeout=20.0, max_retries=0)
    t = time.time()
    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=50,
            messages=[{"role": "user", "content": "Reply with exactly: connection ok"}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        print(f"\nSUCCESS in {time.time() - t:.1f}s — Claude replied: {text!r}")
        print("Your AI reports will work. Run: python -m scripts.generate_report demo true_roas_money_flow")
    except Exception as exc:  # noqa: BLE001 - we want the exact class + message
        print(f"\nFAILED in {time.time() - t:.1f}s")
        print(f"  error type: {type(exc).__name__}")
        print(f"  message:    {str(exc)[:500]}")
        print("\nLikely fix:")
        name = type(exc).__name__.lower()
        if "authentication" in name:
            print("  - The API key is invalid or revoked. Create a new key at console.anthropic.com.")
        elif "permission" in name or "billing" in name or "credit" in name:
            print("  - No billing credit. Add prepaid credits / enable billing at console.anthropic.com.")
        elif "notfound" in name or "model" in name:
            print(f"  - Model '{settings.anthropic_model}' not available to your account. "
                  "Set ANTHROPIC_MODEL in .env to a model you have access to (e.g. claude-sonnet-4-20250514).")
        elif "connection" in name or "timeout" in name or "apiconnection" in name:
            print("  - Network can't reach api.anthropic.com (firewall/proxy/no internet). "
                  "Check connectivity, VPN, or corporate proxy.")
        else:
            print("  - See the message above; often it states the exact cause (credit/model/rate).")


if __name__ == "__main__":
    main()
