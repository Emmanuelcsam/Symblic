"""Offline integrity and independent HTML checks. No provider calls."""
from pathlib import Path
import hashlib,json
import validate_pricing
ROOT=Path(__file__).resolve().parent
evidence=json.loads((ROOT/'evidence.json').read_text())
for name,digest in evidence['artifact_sha256'].items():
    assert Path(name).name==name
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
print(validate_pricing.validate((ROOT/'pricing.html').read_text()))
