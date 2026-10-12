"""Offline integrity and exact-rational checks. No provider calls."""
from pathlib import Path
import hashlib,json
import validate_math
ROOT=Path(__file__).resolve().parent
evidence=json.loads((ROOT/'evidence.json').read_text())
for name,digest in evidence['artifact_sha256'].items():
    assert Path(name).name==name
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
print(validate_math.validate(json.loads((ROOT/'cases.json').read_text()),json.loads((ROOT/'solutions.json').read_text())))
