"""Make an experimental filtered private WAV copy; never changes pipeline settings."""
import argparse
from pathlib import Path
from vet_pipeline.audio_filter import filter_copy, PROFILES
from vet_pipeline.util import write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path, help='Private normalized mono16k PCM16 WAV')
p.add_argument('output', type=Path, help='New private WAV path outside Git')
p.add_argument('--profile', choices=PROFILES, required=True)
a = p.parse_args()
manifest = a.output.with_suffix('.filter.json')
if manifest.exists():
    p.error('Filter manifest already exists; use a new output path')
result = filter_copy(a.source, a.output, a.profile)
write_json(manifest, result)
print('Saved private filtered copy and provenance; no automatic settings changed.')
