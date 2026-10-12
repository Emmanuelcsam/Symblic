"""Independent XML validation of the finite synthetic chart, no rendering or repair."""
import hashlib
import re
import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'


def validate(source):
    def need(ok, why):
        if not ok:
            raise ValueError(why)
    need(isinstance(source, str) and len(source) < 12000, 'bounded SVG string')
    need(not re.search(r'[&]|<!|<\?', source), 'no entities or declarations')
    root = ET.fromstring(source)
    need(root.tag == '{'+NS+'}svg', 'SVG namespace')
    need(root.attrib == {'viewBox':'0 0 360 240','role':'img','aria-labelledby':'chart-title chart-desc'}, 'root attributes')
    need(not (root.text or '').strip(), 'no root text')
    groups = {k:[] for k in ('title','desc','rect','line','text')}
    allowed = {'title':{'id'},'desc':{'id'},'rect':{'x','y','width','height','fill'},
               'line':{'x1','y1','x2','y2','stroke','stroke-width'},
               'text':{'x','y','fill','text-anchor','font-size'}}
    for child in root:
        need(child.tag.startswith('{'+NS+'}'), 'namespace uniformity')
        kind = child.tag[len(NS)+2:]
        need(kind in groups and not list(child), 'direct inert SVG element')
        need(set(child.attrib) == allowed[kind], 'exact safe attributes')
        need(not (child.tail or '').strip(), 'no drawing tail text')
        need(kind in ('title','desc','text') or not (child.text or '').strip(), 'no geometry text')
        groups[kind].append(child)
    need({k:len(v) for k,v in groups.items()} == {'title':1,'desc':1,'rect':3,'line':1,'text':6}, 'exact element counts')
    title, desc = groups['title'][0], groups['desc'][0]
    need(title.attrib['id']=='chart-title' and desc.attrib['id']=='chart-desc', 'accessible IDs')
    need('synthetic' in (title.text or '').lower() and re.search(r'\bms\b',title.text or ''), 'title units')
    need(all(v in (desc.text or '') for v in ('A 2 ms','B 5 ms','C 3 ms')), 'description units and values')
    def color(value):
        return bool(re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', value)) and value.lower() not in ('#fff','#ffffff')
    def nums(el, expected):
        return all(float(el.attrib[k])==v for k,v in expected.items())
    for i, (bar,height) in enumerate(zip(groups['rect'], (40,100,60))):
        need(nums(bar,{'x':40+100*i,'y':180-height,'width':50,'height':height}) and color(bar.attrib['fill']), 'bar geometry and visible fill')
    line=groups['line'][0]
    need(nums(line,{'x1':20,'x2':340,'y1':180,'y2':180,'stroke-width':2}) and color(line.attrib['stroke']), 'baseline')
    for i in range(3):
        for label,y in ((('A','B','C')[i],202),(('2 ms','5 ms','3 ms')[i],(132,72,112)[i])):
            found=[el for el in groups['text'] if (el.text or '').strip()==label]
            need(len(found)==1, 'unique exact label')
            el=found[0]
            need(nums(el,{'x':65+100*i,'y':y,'font-size':14}) and el.attrib['text-anchor']=='middle' and color(el.attrib['fill']), 'visible label geometry')
    return {'passed':True,'bars':3,'values_ms':[2,5,3],'bar_heights':[40,100,60],
            'bar_top_y':[140,80,120],'baseline_y':180,'svg_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'scope':'Finite synthetic SVG structure, accessibility metadata and geometry; no empirical measurement claim.'}
