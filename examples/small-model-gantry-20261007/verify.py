"""Offline integrity and exact geometry/STL checks. No provider calls."""
from pathlib import Path
import hashlib,json
import validate_geometry as V
ROOT=Path(__file__).resolve().parent
evidence=json.loads((ROOT/'evidence.json').read_text())
for name,digest in evidence['artifact_sha256'].items():
    assert Path(name).name==name
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
cases=json.loads((ROOT/'cases.json').read_text());assemblies=json.loads((ROOT/'assemblies.json').read_text())
for case,assembly in zip(cases,assemblies):
    print(case['name'],V.validate(assembly,case['parameters'],case['travel'])['total_material_volume_mm3'],'mm^3')
    if case['name'].endswith('-center'):
        bounds=V.expected_parts(case['parameters'],case['travel'])
        for part in assembly['parts']:
            V.verify_stl((ROOT/(case['name'].split('-')[0]+'-'+part['name']+'.stl')).read_bytes(),part['mesh'],bounds[part['name']])
assert len(cases)==len(assemblies)==6
print('Six geometric mock-ups and ten decoded STLs verified; no physical engineering certification.')
