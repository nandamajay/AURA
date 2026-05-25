from __future__ import annotations
import json
from pathlib import Path
from urllib import request, error

run_dir = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926')
runtime_ids = json.loads((run_dir / 'raw' / 'runtime_ids.json').read_text())
workflow_id = runtime_ids['workflow_id']

# creds
creds = {}
for line in Path('/local/mnt/workspace/AURA_V1/AURA/.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    creds[k.strip()] = v.strip()


def http(method: str, path: str, payload: dict | None = None, token: str | None = None):
    data = None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    req = request.Request(f'http://127.0.0.1:8000{path}', data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            body_raw = resp.read().decode('utf-8', errors='replace')
            try:
                body = json.loads(body_raw)
            except Exception:
                body = {'raw': body_raw}
            return resp.status, body
    except error.HTTPError as e:
        body_raw = e.read().decode('utf-8', errors='replace')
        try:
            body = json.loads(body_raw)
        except Exception:
            body = {'raw': body_raw}
        return e.code, body

status, body = http('POST', '/api/v1/auth/login', {'email': creds['ADMIN_EMAIL'], 'password': creds['ADMIN_PASSWORD']})
if status != 200:
    raise RuntimeError(f'login failed: {status} {body}')
token = body['access_token']

trace = {'workflow_id': workflow_id, 'links': []}
for report in sorted((run_dir / 'reports').glob('*.md')):
    rel = str(report.relative_to(run_dir))
    content = report.read_text(encoding='utf-8', errors='replace')
    status, body = http(
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/evidence',
        {
            'evidence_type': 'patchgen_report',
            'evidence_ref': rel,
            'evidence_content': content,
        },
        token,
    )
    trace['links'].append({'path': rel, 'status': status, 'body': body})

(run_dir / 'raw' / 'runtime_report_link_trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')
print(json.dumps({'linked': len(trace['links'])}, indent=2))
