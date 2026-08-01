from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> int:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("API_KEY")
    api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not api_key:
        print("missing DEEPSEEK_API_KEY", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key, base_url=api_base)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say OK exactly."}],
        temperature=0,
        max_tokens=64,
    )
    message = response.choices[0].message.content or ""
    print(
        {
            "api_base": api_base,
            "model": model,
            "response_id": response.id,
            "message": message,
        }
    )
    return 0 if message.strip() else 1


if __name__ == "__main__":
    raise SystemExit(main())
