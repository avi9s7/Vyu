from __future__ import annotations

from collections.abc import Iterator

DEFAULT_TEXT_SAMPLE_BYTES = 64 * 1024


def bounded_text_sample(chunks: Iterator[bytes], *, max_bytes: int = DEFAULT_TEXT_SAMPLE_BYTES) -> str:
    collected = bytearray()
    for chunk in chunks:
        remaining = max_bytes - len(collected)
        if remaining <= 0:
            break
        collected.extend(chunk[:remaining])
    return collected.decode("utf-8", errors="ignore")
