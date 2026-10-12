"""Independent HTML parsing for the synthetic model-written pricing page."""
from html.parser import HTMLParser
import hashlib
import re


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags=[];self.stack=[];self.text=[];self.style=[];self.doctype=False
    def handle_decl(self, decl):
        if decl.lower()!='doctype html':raise ValueError('unexpected declaration')
        self.doctype=True
    def handle_comment(self, text):
        raise ValueError('comments outside contract')
    def handle_starttag(self, tag, pairs):
        allowed={'html','head','meta','title','style','body','main','h1','div','section','h2','p','button'}
        if tag not in allowed:raise ValueError('unsupported HTML tag')
        attrs=dict(pairs)
        if len(attrs)!=len(pairs):raise ValueError('duplicate HTML attribute')
        if any(k.startswith('on') or k not in {'lang','charset','name','content','class','type'} for k in attrs):raise ValueError('unsupported HTML attribute')
        self.tags.append((tag,attrs,tuple(self.stack)))
        if tag not in {'meta'}:self.stack.append(tag)
    def handle_startendtag(self, tag, pairs):
        if tag!="meta":raise ValueError("only meta is a void element")
        self.handle_starttag(tag,pairs)
    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop()!=tag:raise ValueError('unbalanced HTML')
    def handle_data(self, data):
        if self.stack and self.stack[-1]=='style':self.style.append(data)
        elif data.strip():self.text.append((tuple(self.stack),' '.join(data.split())))


def validate(html):
    def need(ok, why):
        if not ok:raise ValueError(why)
    need(isinstance(html,str) and len(html)<24000,'bounded HTML')
    parser=Page();parser.feed(html);parser.close()
    need(parser.doctype and not parser.stack,'complete HTML document')
    by=lambda tag:[(a,s) for t,a,s in parser.tags if t==tag]
    for tag,n in {'html':1,'head':1,'title':1,'style':1,'body':1,'main':1,'h1':1,'section':3,'h2':3,'p':3,'button':3}.items():
        need(len(by(tag))==n,'exact '+tag+' count')
    need(by('html')[0][0]=={'lang':'en'},'lang=en')
    need(any(a=={'charset':'UTF-8'} or a=={'charset':'utf-8'} for a,_ in by('meta')),'UTF-8 meta')
    need(any(a.get('name')=='viewport' and a.get('content')=='width=device-width, initial-scale=1.0' for a,_ in by('meta')),'viewport')
    need(all(a.get('type')=='button' for a,_ in by('button')),'inert buttons')
    need(all('main' in stack and 'section' in stack for _,stack in by('h2')+by('p')+by('button')),'semantic plan cards')
    title=[v for s,v in parser.text if s[-1]=='title'];need(title==['Pricing Plans'],'page title')
    visible=[v for s,v in parser.text if s[-1]!='title']
    need(visible==['Pricing Plans','Basic','$0','Select','Studio','$12','Select','Team','$30','Select'],'exact visible content')
    css=''.join(parser.style)
    need(not re.search(r'@import|url\s*\(|expression\s*\(',css,re.I),'no active/external CSS')
    need(re.search(r'min\s*\(\s*240px\s*,\s*100%\s*\)',css),'responsive minimum width')
    return {'passed':True,'cards':3,'prices':['$0','$12','$30'],'html_sha256':hashlib.sha256(html.encode()).hexdigest(),
            'scope':'Synthetic HTML structure/data only; responsive visual/focus/contrast checks still required.'}
