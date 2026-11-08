"""Download the two small public CPU speaker models. Never reads clinical data."""
import argparse
from pathlib import Path
import tarfile
import httpx
from vet_pipeline.private import private_path
from vet_pipeline.util import digest_file, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('directory', type=Path)
p.add_argument('--titanet', action='store_true', help='Also install the optional 97 MiB TitaNet-Large embedding candidate; preserve the default manifest')
args = p.parse_args()
root = private_path(args.directory)
root.mkdir(parents=True, exist_ok=True, mode=0o700)
base = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
assets = {
    'sherpa-onnx-pyannote-segmentation-3-0.tar.bz2': base + 'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2',
    'wespeaker_en_voxceleb_resnet34.onnx': base + 'speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx',
}
if args.titanet:
    assets['nemo_en_titanet_large.onnx'] = base + 'speaker-recongition-models/nemo_en_titanet_large.onnx'
with httpx.Client(trust_env=False, follow_redirects=True, timeout=120) as client:
    for name, url in assets.items():
        target = root / name
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.part')
            with client.stream('GET', url) as response:
                response.raise_for_status()
                with temporary.open('wb') as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
            temporary.replace(target)
        print(name, target.stat().st_size, 'bytes')
archive = root / 'sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
with tarfile.open(archive) as source:
    source.extractall(root, filter='data')
write_json(root / ('titanet-models.json' if args.titanet else 'models.json'), {
    'segmentation': str(root / 'sherpa-onnx-pyannote-segmentation-3-0/model.onnx'),
    'embedding': str(root / ('nemo_en_titanet_large.onnx' if args.titanet else 'wespeaker_en_voxceleb_resnet34.onnx')),
    'assets': {name: {'url': url, 'sha256': digest_file(root / name)} for name, url in assets.items()},
    'note': 'Public upstream downloads; SHA256 binds local reuse, not an upstream signature.',
    'embeddingAttribution': 'NVIDIA TitaNet-Large, CC-BY-4.0, https://huggingface.co/nvidia/speakerverification_en_titanet_large' if args.titanet else 'English WeSpeaker VoxCeleb ResNet34 via Sherpa-ONNX',
})
