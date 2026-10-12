"""Offline artifact integrity and independent geometry/XML checks. No provider calls."""
import hashlib
import json
from pathlib import Path
import validate_cup
import validate_chart

ROOT=Path(__file__).resolve().parent
evidence=json.loads((ROOT/'evidence.json').read_text())
for name,digest in evidence['artifact_sha256'].items():
    assert Path(name).name==name, 'Artifact name must stay within this bundle'
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name+' changed'
for name,dims in [('target',[100,80,100,2,2]),('alternate',[37,29,53,1.5,3.25])]:
    mesh=json.loads((ROOT/(name+'-mesh.json')).read_text())
    result=validate_cup.validate(mesh,dims)
    decoded=validate_cup.verify_stl((ROOT/(name+'-cup.stl')).read_bytes(),mesh,dims)
    assert result['passed'] and decoded['passed']
    print(name+': 28 triangles; volume '+str(result['signed_volume_mm3'])+' mm^3; STL verified')
assert validate_chart.validate((ROOT/'chart.svg').read_text())['passed']
print('Chart: exact synthetic bar geometry and accessible SVG structure verified')
print('Finite software checks only; no physical manufacturability or strength certification.')
