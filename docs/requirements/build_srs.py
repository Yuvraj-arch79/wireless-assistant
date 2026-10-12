#!/usr/bin/env python3
"""Build the SRS PDF from its Markdown source. Requires reportlab >= 4.

Run: python build_srs.py --source wireless-assistant-srs.md --output wireless-assistant-srs.pdf
The small Markdown subset used by this document is deliberate and documented.
"""
import argparse
import html
import json
import re
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle, Flowable, Spacer

NAVY = colors.HexColor('#102B46')
TEAL = colors.HexColor('#087F8C')
INK = colors.HexColor('#172F44')
MUTED = colors.HexColor('#526676')
LINE = colors.HexColor('#D9E3EA')
PALE = colors.HexColor('#F1F6F9')
WHITE = colors.white
W, H = A4
LEFT = 47
RIGHT = 47
WIDTH = W-LEFT-RIGHT

def init_fonts(font_dir=None):
    candidates = [Path(font_dir)] if font_dir else []
    candidates += [Path('/usr/share/fonts/truetype/dejavu'), Path('/usr/local/share/fonts')]
    for base in candidates:
        normal=base/'DejaVuSans.ttf'; bold=base/'DejaVuSans-Bold.ttf'
        if normal.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont('Body',str(normal)))
            pdfmetrics.registerFont(TTFont('BodyBold',str(bold)))
            pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
            return
    raise SystemExit('Install DejaVu Sans or pass --font-dir containing DejaVuSans.ttf and DejaVuSans-Bold.ttf.')

def rich(text):
    s=html.escape(text)
    s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font color="#087F8C">\1</font>',s)
    s=re.sub(r'https://[^\s<]+',lambda m:f'<link href="{m.group(0)}" color="#087F8C">{m.group(0)}</link>',s)
    return s

def parse_source(path):
    text=path.read_text(encoding='utf-8')
    chunks=re.split(r'^## ',text,flags=re.M)
    meta={k.lower():v.strip() for k,v in re.findall(r'^\*\*([^*]+):\*\* (.+)$',chunks[0],re.M)}
    pages=[]
    for chunk in chunks[1:]:
        lines=chunk.splitlines(); title=lines.pop(0).strip(); subtitle=''; blocks=[]; i=0; widths=None
        while i<len(lines):
            s=lines[i].strip()
            if not s: i+=1; continue
            if s.startswith('*') and not s.startswith('**') and s.endswith('*') and not subtitle:
                subtitle=s[1:-1]; i+=1; continue
            if s.startswith('<!-- widths:'):
                widths=[float(v) for v in s.split(':',1)[1].split('-->')[0].strip().split(',')]; i+=1;continue
            if s.startswith('### '):
                heading=s[4:]; match=re.match(r'([A-Z]+-\d{2}) - (.+)',heading)
                if match:
                    collected=[]; i+=1
                    while i<len(lines) and not lines[i].startswith('### '):
                        current=lines[i].strip()
                        if current: collected.append(current)
                        i+=1
                        if current.startswith('**Check:** '): break
                    status=next(v[len('**Status:** '):] for v in collected if v.startswith('**Status:** '))
                    check=next(v[len('**Check:** '):] for v in collected if v.startswith('**Check:** '))
                    desc=' '.join(v for v in collected if not v.startswith('**Status:** ') and not v.startswith('**Check:** '))
                    blocks.append(dict(kind='req',id=match[1],title=match[2],status=status,text=desc,check=check))
                else: blocks.append(dict(kind='h',text=heading)); i+=1
                continue
            if s.startswith('|'):
                raw=[]
                while i<len(lines) and lines[i].strip().startswith('|'):
                    raw.append([v.strip() for v in lines[i].strip().strip('|').split('|')]);i+=1
                blocks.append(dict(kind='table',headers=raw[0],rows=raw[2:],widths=widths)); widths=None;continue
            if s.startswith('> '):
                quote=[]
                while i<len(lines) and lines[i].strip().startswith('> '):
                    quote.append(lines[i].strip()[2:]);i+=1
                titleq=quote[0].strip('*')
                blocks.append(dict(kind='note',title=titleq,text=' '.join(quote[1:])));continue
            if s.startswith('- '):
                items=[]
                while i<len(lines) and lines[i].strip().startswith('- '):
                    items.append(lines[i].strip()[2:]);i+=1
                blocks.append(dict(kind='bullets',items=items));continue
            if s=='```mermaid':
                i+=1
                while i<len(lines) and lines[i].strip()!='```':i+=1
                i+=1; blocks.append(dict(kind='workflow'));continue
            para=[s];i+=1
            while i<len(lines) and lines[i].strip():
                para.append(lines[i].strip());i+=1
            blocks.append(dict(kind='p',text=' '.join(para)))
        pages.append(dict(title=title,subtitle=subtitle,blocks=blocks))
    return meta,pages

class Workflow(Flowable):
    def __init__(self): super().__init__();self.width=WIDTH;self.height=334
    def draw(self):
        c=self.canv
        def box(x,y,w,h,label,accent=False):
            c.setFillColor(TEAL if accent else PALE); c.setStrokeColor(TEAL if accent else LINE)
            c.roundRect(x,y,w,h,5,fill=1,stroke=1)
            ps=ParagraphStyle('box',fontName='BodyBold' if accent else 'Body',fontSize=8.5,leading=11,alignment=1,textColor=WHITE if accent else INK)
            para=Paragraph(rich(label),ps);pw,ph=para.wrap(w-12,h-8);para.drawOn(c,x+6,y+(h-ph)/2)
        def arrow(points,label=None,lx=0,ly=0):
            c.setStrokeColor(MUTED);c.setLineWidth(.9);p=c.beginPath();p.moveTo(*points[0])
            for pt in points[1:]:p.lineTo(*pt)
            c.drawPath(p)
            x1,y1=points[-2];x2,y2=points[-1];dx=x2-x1;dy=y2-y1
            mag=(dx*dx+dy*dy)**.5; ux=dx/mag;uy=dy/mag
            p=c.beginPath();p.moveTo(x2,y2);p.lineTo(x2-5*ux+2.5*uy,y2-5*uy-2.5*ux);p.lineTo(x2-5*ux-2.5*uy,y2-5*uy+2.5*ux);p.close()
            c.setFillColor(MUTED);c.drawPath(p,fill=1,stroke=0)
            if label:c.setFont('Body',7.3);c.setFillColor(MUTED);c.drawString(lx,ly,label)
        box(137,293,227,34,'User question + relevant recent context',True)
        box(137,243,227,35,'Domain check + A resolves the need')
        box(0,235,113,45,'Ask user and pause')
        box(388,235,113,45,'Explain scope')
        arrow([(250,293),(250,278)])
        arrow([(137,261),(113,261)],'Clarify',113,283)
        arrow([(364,261),(388,261)],'Unrelated',364,283)
        box(137,190,227,35,'A requests; backend retrieves sources')
        arrow([(250,243),(250,225)])
        box(137,137,227,35,'B writes the answer + citations')
        arrow([(250,190),(250,172)])
        box(137,84,227,35,'Code checks records; C judges meaning')
        arrow([(250,137),(250,119)])
        box(0,13,155,46,'Display the exact eligible B answer',True)
        box(173,13,155,46,'Specific issue + useful repair + budget?')
        box(347,13,154,46,'Use eligible result or explain inability')
        arrow([(190,84),(190,72),(78,72),(78,59)],'Eligible',93,77)
        arrow([(250,84),(250,59)])
        arrow([(328,36),(347,36)],'No',332,43)
        arrow([(289,59),(377,59),(377,207),(364,207)],'Yes',379,143)
        c.setFont('Body',7.1);c.setFillColor(MUTED);c.drawString(7,211,'Reply returns to A')
        arrow([(55,235),(55,225),(124,225),(124,248),(137,248)])
        c.setFont('BodyBold',7.5);c.drawString(142,0,'One initial draft + at most two correction rounds')

def styles(scale=1):
    return {
        'body':ParagraphStyle('body',fontName='Body',fontSize=10.3*scale,leading=14.4*scale,textColor=INK,spaceAfter=7*scale),
        'h':ParagraphStyle('h',fontName='BodyBold',fontSize=11.2*scale,leading=15*scale,textColor=NAVY,spaceBefore=4*scale,spaceAfter=5*scale),
        'small':ParagraphStyle('small',fontName='Body',fontSize=9.1*scale,leading=12.5*scale,textColor=MUTED),
        'cell':ParagraphStyle('cell',fontName='Body',fontSize=9.25*scale,leading=12.6*scale,textColor=INK),
        'th':ParagraphStyle('th',fontName='BodyBold',fontSize=9.2*scale,leading=12.2*scale,textColor=WHITE),
        'reqtitle':ParagraphStyle('reqtitle',fontName='BodyBold',fontSize=10.0*scale,leading=13.4*scale,textColor=NAVY),
        'reqbody':ParagraphStyle('reqbody',fontName='Body',fontSize=9.85*scale,leading=13.3*scale,textColor=INK),
        'check':ParagraphStyle('check',fontName='Body',fontSize=8.8*scale,leading=11.8*scale,textColor=MUTED),
    }

def flowables(blocks,scale):
    st=styles(scale); fs=[]
    for b in blocks:
        k=b['kind']
        if k in ('p','h'):
            fs.append(Paragraph(rich(b['text']),st['body' if k=='p' else 'h']))
            fs.append(Spacer(1,7*scale if k=='p' else 5*scale))
        elif k=='bullets':
            for item in b['items']:
                ps=ParagraphStyle('bullet',parent=st['body'],leftIndent=11,firstLineIndent=-9)
                fs.append(Paragraph('-  '+rich(item),ps));fs.append(Spacer(1,4*scale))
            fs.append(Spacer(1,4*scale))
        elif k=='table':
            heads=[Paragraph(rich(x),st['th']) for x in b['headers']]
            rows=[[Paragraph(rich(x),st['cell']) for x in row] for row in b['rows']]
            widths=b.get('widths') or [1/len(heads)]*len(heads)
            tab=Table([heads]+rows,colWidths=[WIDTH*v for v in widths],hAlign='LEFT')
            commands=[('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6*scale),('BOTTOMPADDING',(0,0),(-1,-1),6*scale),('LINEBELOW',(0,0),(-1,0),.6,NAVY)]
            for i in range(1,len(rows)+1):
                commands.append(('BACKGROUND',(0,i),(-1,i),PALE if i%2 else WHITE))
                commands.append(('LINEBELOW',(0,i),(-1,i),.35,LINE))
            tab.setStyle(TableStyle(commands));fs += [tab,Spacer(1,10*scale)]
        elif k=='note':
            content=Paragraph('<b>'+rich(b['title'])+'</b><br/>'+rich(b['text']),st['small'])
            tab=Table([[content]],colWidths=[WIDTH]);tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LINEBEFORE',(0,0),(-1,-1),2.2,TEAL),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));fs += [tab,Spacer(1,9*scale)]
        elif k=='req':
            statuscolor='#087F8C' if b['status']=='CONFIRMED' else '#6B6B78'
            head=Paragraph(rich(b['id'])+'  '+rich(b['title'])+f' <font name="Body" size="7.3" color="{statuscolor}"> / {b["status"]}</font>',st['reqtitle'])
            body=Paragraph(rich(b['text']),st['reqbody'])
            check=Paragraph('<b>Check:</b> '+rich(b['check']),st['check'])
            tab=Table([[head],[body],[check]],colWidths=[WIDTH]);tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,0),0),('TOPPADDING',(0,1),(-1,-1),2*scale),('BOTTOMPADDING',(0,0),(-1,-1),1*scale),('LINEBELOW',(0,-1),(-1,-1),.35,LINE)]));fs += [tab,Spacer(1,8*scale)]
        elif k=='workflow':fs += [Workflow(),Spacer(1,9*scale)]
        else:raise ValueError(k)
    return fs

def measure(fs):
    return sum(f.wrap(WIDTH,10000)[1] for f in fs)

def footer(c,page,total,version):
    c.setStrokeColor(LINE);c.setLineWidth(.5);c.line(LEFT,42,W-RIGHT,42)
    c.setFillColor(MUTED);c.setFont('Body',7.5)
    c.drawString(LEFT,28,f'WA-SRS-001  |  v{version}  |  Review draft')
    c.drawRightString(W-RIGHT,28,f'{page:02d} / {total:02d}')

def cover(c,meta,total):
    c.setFillColor(NAVY);c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(TEAL);c.rect(LEFT,H-83,54,5,fill=1,stroke=0)
    c.setFont('BodyBold',10);c.setFillColor(colors.HexColor('#A8DDE0'));c.drawString(LEFT,H-108,'PRODUCT REQUIREMENTS / FIRST RELEASE')
    c.setFillColor(WHITE);c.setFont('BodyBold',40);c.drawString(LEFT,H-194,'Wireless')
    c.drawString(LEFT,H-244,'Assistant')
    c.setFont('Body',20);c.drawString(LEFT,H-292,'Software Requirements')
    c.drawString(LEFT,H-322,'Specification')
    ps=ParagraphStyle('cover',fontName='Body',fontSize=12,leading=18,textColor=colors.HexColor('#D0E0EA'))
    para=Paragraph('A clear, evidence-backed cellular assistant that understands the question, remembers relevant context and explains its limits.',ps)
    pw,ph=para.wrap(420,120);para.drawOn(c,LEFT,H-388-ph)
    c.setStrokeColor(colors.HexColor('#436176'));c.line(LEFT,218,W-RIGHT,218)
    c.setFont('BodyBold',11);c.setFillColor(WHITE);c.drawString(LEFT,188,'VERSION '+meta.get('version','0.9')+'  /  REVIEW DRAFT')
    c.setFont('Body',10);c.setFillColor(colors.HexColor('#BCD1DD'));c.drawString(LEFT,165,meta.get('date','12 October 2026'))
    c.drawString(LEFT,140,meta.get('repository','Wireless Assistant'))
    c.setFont('Body',9);c.drawString(LEFT,83,'Prepared from the agreed design and edited product problem statement.')
    c.drawString(LEFT,67,'Open decisions and proposed safeguards are explicitly identified.')
    c.showPage()

def contents(c,pages,total,meta):
    c.setFillColor(NAVY);c.setFont('BodyBold',27);c.drawString(LEFT,H-82,'Contents')
    c.setFont('Body',10);c.setFillColor(MUTED);c.drawString(LEFT,H-108,'Read the product story first; use requirement IDs when building and testing.')
    y=H-143
    for i,p in enumerate(pages):
        key=f'section-{i+1}';c.setFont('BodyBold',9.2);c.setFillColor(TEAL);c.drawString(LEFT,y,f'{i+1:02d}')
        c.setFont('Body',9.3);c.setFillColor(INK);c.drawString(LEFT+28,y,p['title'])
        c.setFillColor(MUTED);c.drawRightString(W-RIGHT,y,str(i+3))
        c.linkRect('',key,(LEFT,y-3,W-RIGHT,y+11),relative=0,thickness=0)
        y-=18.1
    footer(c,2,total,meta.get('version','0.9'));c.showPage()

def build(source,output,font_dir=None,report=None):
    init_fonts(font_dir);meta,pages=parse_source(source);output.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(output),pagesize=A4,pageCompression=1,invariant=1)
    c.setTitle('Wireless Assistant - Software Requirements Specification')
    c.setAuthor('Wireless Assistant project')
    c.setSubject('Plain-English requirements, A/B/C workflow, 3GPP RAG and acceptance criteria')
    total=len(pages)+2;cover(c,meta,total);contents(c,pages,total,meta);stats=[]
    for i,page in enumerate(pages):
        pnum=i+3;c.bookmarkPage(f'section-{i+1}');c.addOutlineEntry(page['title'],f'section-{i+1}',0,False)
        c.setFont('Body',7.7);c.setFillColor(MUTED);c.drawString(LEFT,H-30,'WIRELESS ASSISTANT / SOFTWARE REQUIREMENTS')
        c.setFont('BodyBold',8.8);c.setFillColor(TEAL);c.drawString(LEFT,H-65,page['subtitle'].upper())
        title=Paragraph(rich(page['title']),ParagraphStyle('title',fontName='BodyBold',fontSize=23,leading=28,textColor=NAVY))
        tw,th=title.wrap(WIDTH,100);title.drawOn(c,LEFT,H-80-th);y=H-97-th
        available=y-57;chosen=None
        for scale in [1,.98,.96,.94]:
            fs=flowables(page['blocks'],scale);used=measure(fs)
            if used<=available:chosen=(fs,scale,used);break
        if chosen is None:raise ValueError(f'Page {pnum} overflows: {page["title"]}: needs {used:.1f}, available {available:.1f}')
        fs,scale,used=chosen
        for f in fs:
            fw,fh=f.wrap(WIDTH,10000);y-=fh;f.drawOn(c,LEFT,y)
        footer(c,pnum,total,meta.get('version','0.9'));c.showPage()
        stats.append(dict(page=pnum,title=page['title'],scale=scale,used=round(used,1),available=round(available,1),bottom=round(y,1)))
    c.save()
    if report:report.write_text(json.dumps(dict(pages=total,layout=stats),indent=2))
    print(f'Built {output.name}: {total} pages; {len([b for p in pages for b in p["blocks"] if b["kind"]=="req"])} requirements')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=Path(__file__).with_name('wireless-assistant-srs.md'));ap.add_argument('--output',type=Path,default=Path(__file__).with_name('wireless-assistant-srs.pdf'));ap.add_argument('--font-dir');ap.add_argument('--layout-report',type=Path)
    a=ap.parse_args();build(a.source,a.output,a.font_dir,a.layout_report)
