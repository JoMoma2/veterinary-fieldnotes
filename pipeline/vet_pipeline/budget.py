"""Offline whole-message budgeting. No clinical text is sent to a tokenizer service."""

from __future__ import annotations
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from .locations import local_path


@lru_cache(maxsize=8)
def _tokenizer(path, modified, size, expected):
    from tokenizers import Tokenizer

    file = local_path(path)
    if expected and hashlib.sha256(file.read_bytes()).hexdigest() != expected:
        raise ValueError("Configured tokenizer checksum does not match")
    tokenizer = Tokenizer.from_file(str(file))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


def messages_budget(messages, provider):
    configured = provider.get("tokenizer_path", "")
    wrapper = provider.get("chat_overhead_tokens", 64)
    safety = provider.get("context_safety_tokens", 128)
    tokenizer = None
    if configured:
        path = local_path(configured).expanduser().resolve()
        if not path.is_file():
            raise ValueError(
                "Configured offline tokenizer file is missing; no automatic download is allowed"
            )
        stat = path.stat()
        tokenizer = _tokenizer(
            str(path),
            stat.st_mtime_ns,
            stat.st_size,
            provider.get("tokenizer_sha256", ""),
        )
    counts = []
    for message in messages:
        text = message["content"]
        # Unknown tokenizers use a deliberately conservative UTF-8 byte bound,
        # rather than an English chars/4 guess that misses identifier-heavy JSON.
        count = (
            len(tokenizer.encode(text, add_special_tokens=False).ids)
            if tokenizer
            else len(text.encode("utf-8"))
        )
        counts.append({"role": message["role"], "tokens": count})
    prompt = sum(m["tokens"] for m in counts) + wrapper
    output = provider["max_output_tokens"]
    window = provider["context_window"]
    return {
        "method": "offline-tokenizer-plus-chat-allowance"
        if tokenizer
        else "conservative-utf8-bytes-plus-chat-allowance",
        "messages": counts,
        "estimatedPromptTokens": prompt,
        "chatAllowance": wrapper,
        "safetyTokens": safety,
        "reservedOutputTokens": output,
        "contextWindow": window,
        "fits": prompt + output + safety <= window,
    }


def transcript_hash(transcript):
    return hashlib.sha256(
        json.dumps(transcript, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
