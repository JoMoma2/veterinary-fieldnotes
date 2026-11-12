"""Small local structured-inference adapter for publication-only processing."""
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from jsonschema import Draft202012Validator
from .budget import messages_budget
from .evaluation import verified_local_model
from .resources import check_resources
from .util import write_json


def ask_json(messages, schema, cfg, raw_path: Path):
    p = cfg['provider']; endpoint = urlsplit(p['base_url'])
    if (p['kind'] != 'ollama' or endpoint.hostname not in ['localhost', '127.0.0.1', '::1']
            or endpoint.port != 11434 or endpoint.path not in ['', '/']
            or endpoint.username or endpoint.query or endpoint.fragment):
        raise ValueError('Publication reasoning requires direct local Ollama')
    verified_local_model(cfg)
    if not messages_budget(messages, p)['fits']:
        raise ValueError('Complete publication request does not fit; no truncation')
    check_resources(cfg, 'extract')
    with httpx.Client(timeout=p['timeout_seconds'], trust_env=False) as client:
        response = client.post(p['base_url'].rstrip('/') + '/api/chat', json={
            'model': p['model'], 'messages': messages, 'format': schema, 'think': True,
            'stream': False, 'keep_alive': '2m', 'options': {
                'num_ctx': p['context_window'], 'num_predict': p['max_output_tokens'],
                'num_gpu': cfg['shift_context']['gpu_layers'], 'temperature': .2,
                'top_p': .95, 'top_k': 20, 'min_p': 0, 'repeat_penalty': 1.0}})
        response.raise_for_status(); raw = response.json()
    if raw_path.exists():
        shutil.copyfile(raw_path, raw_path.with_name(raw_path.stem + '-previous-' + str(time.time_ns()) + raw_path.suffix))
    write_json(raw_path, raw)
    if not raw.get('done') or raw.get('done_reason') == 'length':
        raise ValueError('Incomplete publication reasoning; retain for review')
    result = json.loads(raw['message']['content'])
    Draft202012Validator(schema).validate(result)
    return result
