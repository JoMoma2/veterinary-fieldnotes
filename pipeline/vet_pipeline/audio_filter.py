"""Conservative, opt-in audio experiments. Never used by automatic processing.

Uses the already optional PyAV/libavfilter dependency, not an external service.
Filter meanings: https://ffmpeg.org/ffmpeg-filters.html#highpass and #afftdn.
"""
from fractions import Fraction
import os
import tempfile
import wave

from .private import private_path
from .util import digest_file


PROFILES = {
    "highpass": [("highpass", "f=80:p=2:r=f64")],
    "denoise": [
        ("highpass", "f=80:p=2:r=f64"),
        ("afftdn", "nr=6:nf=-50:tn=1:gs=5"),
    ],
}


def filter_copy(source, target, profile):
    """Create a new private mono16k PCM16 WAV, preserving length and time origin.

    Reject overwrites, unexpected audio formats, changed inputs, and discontinuous
    output. No normalization, silence removal, or source edits. afftdn's measured
    two-hop delay (400 samples at 16 kHz) is flushed with silence and removed;
    impulse regression tests include speech-time equivalents near the file end.
    The denoiser is experimental: cleaner sound does not prove better ASR.
    """
    import av

    source, target = private_path(source), private_path(target)
    if profile not in PROFILES:
        raise ValueError("Unknown audio experiment profile")
    if source == target or target.exists():
        raise ValueError("Choose a new filtered copy; existing files are never overwritten")
    before = digest_file(source)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".filter-", suffix=".wav", dir=target.parent)
    os.close(fd)
    try:
        with wave.open(str(source), "rb") as original:
            if (original.getnchannels(), original.getsampwidth(), original.getframerate(), original.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Filtering requires a separate mono16k PCM16 working copy")
            expected = original.getnframes()
            if expected <= 0 or expected > 900 * 16000:
                raise ValueError("Keep filter experiments between one sample and 15 minutes")
            graph = av.filter.Graph()
            inlet = graph.add_abuffer(sample_rate=16000, format="s16", layout="mono", time_base=Fraction(1, 16000))
            nodes = [inlet] + [graph.add(name, options) for name, options in PROFILES[profile]]
            nodes += [graph.add("aformat", "sample_fmts=s16:sample_rates=16000:channel_layouts=mono"), graph.add("abuffersink")]
            graph.link_nodes(*nodes)
            graph.configure()
            delay = 400 if profile == "denoise" else 0
            written = raw_samples = 0
            with wave.open(temporary, "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)

                def drain(flushing=False):
                    nonlocal written, raw_samples
                    while True:
                        try:
                            frame = nodes[-1].pull()
                        except av.error.BlockingIOError:
                            if flushing:
                                raise ValueError("Filter did not finish flushing") from None
                            return
                        except av.error.EOFError:
                            return
                        if frame.sample_rate != 16000 or frame.format.name != "s16" or frame.layout.name != "mono" or frame.pts is None or frame.time_base is None or frame.pts * frame.time_base != Fraction(raw_samples, 16000):
                            raise ValueError("Filter changed audio format or timestamp continuity")
                        skip = min(frame.samples, max(0, delay - raw_samples))
                        output.writeframesraw(bytes(frame.planes[0])[skip * 2:frame.samples * 2])
                        raw_samples += frame.samples
                        written += frame.samples - skip

                read = 0
                while data := original.readframes(4096):
                    frame = av.AudioFrame(format="s16", layout="mono", samples=len(data) // 2)
                    frame.sample_rate = 16000
                    frame.time_base = Fraction(1, 16000)
                    frame.pts = read
                    frame.planes[0].update(data + b"\0" * (frame.planes[0].buffer_size - len(data)))
                    read += frame.samples
                    inlet.push(frame)
                    drain()
                if delay:
                    tail = av.AudioFrame(format="s16", layout="mono", samples=delay)
                    tail.sample_rate = 16000
                    tail.time_base = Fraction(1, 16000)
                    tail.pts = read
                    tail.planes[0].update(b"\0" * tail.planes[0].buffer_size)
                    inlet.push(tail)
                    drain()
                inlet.push(None)
                drain(flushing=True)
            if read != expected or written != expected or raw_samples != expected + delay:
                raise ValueError("Filter changed sample count; refusing uncertain time alignment")
        if digest_file(source) != before:
            raise ValueError("Source changed during filtering")
        with open(temporary, "rb") as completed:
            os.fsync(completed.fileno())
        # Hard-link installs atomically and fails if another process created target.
        os.link(temporary, target)
        directory = os.open(target.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return {"profile": profile, "filters": PROFILES[profile], "sourceSha256": before,
                "outputSha256": digest_file(target), "samples": written,
                "sampleRate": 16000, "durationSeconds": written / 16000,
                "timeOriginOffsetSeconds": 0, "compensatedDelaySamples": delay,
                "flushPaddingSamples": delay, "avVersion": av.__version__,
                "libavfilterVersion": list(av.library_versions["libavfilter"])}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
