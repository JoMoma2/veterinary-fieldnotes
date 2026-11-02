"""PCM conversion for generated test speech only; never edits recorder media."""

from array import array
import sys


def resample_pcm16_mono(
    data: bytes, source_rate: int, target_rate: int = 16000
) -> bytes:
    if source_rate <= 0 or target_rate <= 0 or len(data) % 2:
        raise ValueError("Invalid synthetic PCM buffer or sample rate")
    if source_rate == target_rate:
        return data
    source = array("h")
    source.frombytes(data)
    if sys.byteorder != "little":
        source.byteswap()
    if not source:
        return b""
    result = array("h")
    for i in range(round(len(source) * target_rate / source_rate)):
        position = i * source_rate / target_rate
        j = min(int(position), len(source) - 1)
        fraction = position - j
        result.append(
            round(
                source[j] * (1 - fraction)
                + source[min(j + 1, len(source) - 1)] * fraction
            )
        )
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()
