from pathlib import Path
from xml.etree import ElementTree as E
from html import escape
import json

OUT=Path(__file__).resolve().parents[1] / 'docs' / 'design' / 'diagrams'
OUT.mkdir(parents=True, exist_ok=True)
pages=[]
def page(name,title,subtitle,w=1600,h=1250):
    p={'name':name,'title':title,'subtitle':subtitle,'w':w,'h':h,'nodes':[],'edges':[],'bands':[]}
    pages.append(p); return p
def node(p,id,x,y,w,h,title,lines,color='#e8f0fd'):
    p['nodes'].append(dict(id=id,x=x,y=y,w=w,h=h,title=title,lines=lines,color=color))
def edge(p,a,b,label='',points=None,dashed=False):
    p['edges'].append(dict(a=a,b=b,label=label,points=points,dashed=dashed))
def band(p,y,text): p['bands'].append((y,text))
p=page('Data delivery','Release 1 · Data delivery and evidence','Reference workflow and operator access · The dashboard and MCP use the same workspace projections')
band(p,145,'SOURCE EVIDENCE')
node(p,'job',60,190,440,135,'Batch orchestrator',['Reports job attempts and lineage'])
node(p,'files',580,190,440,135,'Object storage',['List partition metadata and object counts'])
node(p,'warehouse',1100,190,440,135,'Warehouse',['Observe schema and sink publication'])
node(p,'ingest',60,440,440,150,'Ingestion API',['Validate, deduplicate and store evidence','Receive monitoring and paging webhooks'])
node(p,'db',580,440,440,150,'Workspace database',['Assets, runs, fields, edges and receipts','Shared PostgreSQL for multiple replicas'])
node(p,'views',1100,440,440,150,'Authorized views',['Availability, quality, impact and coverage','Links to evidence and external incidents'])
for id,x in [('job',280),('files',800),('warehouse',1320)]:
    edge(p,id,'ingest',points=[(x,325),(x,365),(280,365),(280,440)])
edge(p,'ingest','db',points=[(500,510),(580,510)])
edge(p,'db','views',points=[(1020,510),(1100,510)])
band(p,675,'OPERATOR ACCESS')
node(p,'llm',60,735,440,145,'Configured LLM endpoint',['Approved free model and provider','Receives permitted context'])
node(p,'agent',580,735,440,145,'Chat agent',['User session and delegated grant','Report unknown and cite evidence'])
node(p,'mcp',1100,735,440,145,'Read-only MCP',['Validate user, workspace and scope','One tool per live view'])
edge(p,'agent','llm',points=[(580,800),(500,800)])
edge(p,'agent','mcp',points=[(1020,800),(1100,800)])
edge(p,'mcp','views',points=[(1320,735),(1320,590)])
node(p,'human',580,980,440,125,'Operator',['Monitor deliveries and investigate impact'])
node(p,'ui',1100,980,440,125,'Live dashboard',['Same caller-scoped response fields'])
edge(p,'human','agent',points=[(800,980),(800,880)])
edge(p,'human','ui',points=[(1020,1040),(1100,1040)])
edge(p,'ui','views',points=[(1540,1040),(1570,1040),(1570,510),(1540,510)])

p=page('Availability and delivery','Availability · durable acknowledgements and recovery','Production spreads replicas across zones; local Kubernetes exercises coordination, not independent-zone resilience',1600,1200)
band(p,145,'01  STATELESS EDGE AND PROCESS REPLICAS')
node(p,'gate',550,180,500,100,'HTTPS gateway / service',['Authorization remains inside application services'],'#e8f7f3')
for i,zone in enumerate(['Zone A','Zone B','Zone C']):
    x=60+i*520
    node(p,'z'+str(i),x,370,440,190,zone,['API replica','Processor capacity (A / B minimum)','Scheduler capacity (A / B minimum)','Connector pools spread by criticality'],'#eef0ff')
    edge(p,'gate','z'+str(i),'route',[(800,280),(800,320),(x+220,320),(x+220,370)])
band(p,620,'02  DATABASE FAILOVER — application replication depends on durable shared state')
node(p,'primary',60,675,440,150,'PostgreSQL writer',['Inbox + queue + projections','Synchronous policy chosen explicitly','Client retries resolve uncertain commits'],'#fff3df')
node(p,'standby',580,675,440,150,'Cross-zone standby',['Automated failover + writer fencing','Acknowledged-event durability depends','on replication and failover policy'],'#fff3df')
node(p,'backup',1100,675,440,150,'Backups + PITR',['Separate disaster-recovery procedure','Restricted access + restore tests','No active-active region writes in R1'],'#f1f3f5')
for i in range(3):
    x=280+i*520
    edge(p,'z'+str(i),'primary','DB endpoint' if i==0 else '',[(x,560),(x,600),(280,600),(280,675)])
edge(p,'primary','standby','replicate',[(500,750),(580,750)])
edge(p,'standby','backup','archive / backup',[(1020,750),(1100,750)],True)
band(p,875,'03  DELIVERY RULES — at-least-once transport, idempotent effects; no exactly-once claim')
node(p,'accept',60,925,440,165,'1 · Accept',['Validate → inbox + task transaction','Commit before 202 receipt','Retry returns existing receipt'],'#e8f7f3')
node(p,'work',580,925,440,165,'2 · Process',['Claim with expiry + fencing generation','Apply projection + processing marker','Replay safe after worker crash'],'#e8f7f3')
node(p,'cursor',1100,925,440,165,'3 · Advance / recover',['Advance cursor after durable receipts','Reject stale task completion','Report collector loss separately'],'#e8f7f3')
edge(p,'accept','work',points=[(500,1005),(580,1005)])
edge(p,'work','cursor',points=[(1020,1005),(1100,1005)])

mx=E.Element('mxfile',host='app.diagrams.net',version='24.7.17')
for idx,p in enumerate(pages):
    d=E.SubElement(mx,'diagram',id='page-'+str(idx),name=p['name'])
    model=E.SubElement(d,'mxGraphModel',dx=str(p['w']),dy=str(p['h']),grid='1',gridSize='10',page='1',pageWidth=str(p['w']),pageHeight=str(p['h']))
    root=E.SubElement(model,'root');E.SubElement(root,'mxCell',id='0');E.SubElement(root,'mxCell',id='1',parent='0')
    def cell(id,value,x,y,w,h,style):
        c=E.SubElement(root,'mxCell',id=id,value=value,style=style,vertex='1',parent='1')
        E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
    cell('title',p['title'],50,30,p['w']-100,50,'text;html=0;fontSize=30;fontStyle=1;align=left;')
    cell('subtitle',p['subtitle'],50,85,p['w']-100,40,'text;html=0;fontSize=16;align=left;')
    for j,(y,t) in enumerate(p['bands']):cell('band'+str(j),t,50,y,p['w']-100,30,'text;html=0;fontSize=16;fontStyle=1;align=left;fontColor=#536176;')
    for n in p['nodes']:
        cell(n['id'],n['title']+'\n\n'+'\n'.join(n['lines']),n['x'],n['y'],n['w'],n['h'],'rounded=1;whiteSpace=wrap;html=0;align=left;verticalAlign=middle;spacing=18;fontSize=16;fillColor='+n['color']+';strokeColor=#b8c4d4;')
    for j,e in enumerate(p['edges']):
        c=E.SubElement(root,'mxCell',id='edge'+str(j),value=e['label'],style='edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;fontSize=13;strokeColor=#68768a;'+('dashed=1;' if e['dashed'] else ''),edge='1',parent='1',source=e['a'],target=e['b'])
        g=E.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        if e['points'] and len(e['points'])>2:
            a=E.SubElement(g,'Array',attrib={'as':'points'})
            for x,y in e['points'][1:-1]: E.SubElement(a,'mxPoint',x=str(x),y=str(y))

xml=E.tostring(mx,encoding='unicode')
(OUT/'release1_architecture.drawio').write_text(xml)
def svg(p):
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{p["w"]}" height="{p["h"]}" viewBox="0 0 {p["w"]} {p["h"]}" content="{escape(xml,quote=True)}">', '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#68768a"/></marker></defs>', '<rect width="100%" height="100%" fill="#ffffff"/>']
    def text(x,y,t,size=17,weight='400',color='#25334a'):
        s.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(t)}</text>')
    text(50,65,p['title'],32,'700');text(50,105,p['subtitle'],16)
    for y,t in p['bands']:
        text(50,y+22,t,16,'700','#536176')
    for e in p['edges']:
        pts=e['points']
        if not pts:
            a=next(n for n in p['nodes'] if n['id']==e['a']);b=next(n for n in p['nodes'] if n['id']==e['b'])
            pts=[(a['x']+a['w']/2,a['y']+a['h']),(b['x']+b['w']/2,b['y'])]
        s.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in pts)+'" fill="none" stroke="#68768a" stroke-width="2" marker-end="url(#arrow)"'+(' stroke-dasharray="7 5"' if e['dashed'] else '')+'/>')
        if e['label']:
            x=(pts[0][0]+pts[1][0])/2;y=(pts[0][1]+pts[1][1])/2
            text(x+8,y-7,e['label'],13,'400','#536176')
    for n in p['nodes']:
        s.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" rx="14" fill="{n["color"]}" stroke="#b8c4d4"/>')
        text(n['x']+18,n['y']+34,n['title'],21,'700')
        for i,line in enumerate(n['lines']):text(n['x']+18,n['y']+65+i*24,line,16)
    text(50,p['h']-35,'Design proposal · Solid: event/control/state path · Dashed: polling or optional integration · Sizes and replica counts require validation',14,color='#536176')
    s.append('</svg>');return ''.join(s)
svgs=[svg(p) for p in pages]
for name,data in zip(['release1_architecture.svg','release1_availability.svg'],svgs):(OUT/name).write_text(data)
html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Release 1 architecture</title><style>body{margin:0;background:#edf1f6;color:#25334a;font:16px Arial,sans-serif}header{padding:24px 32px;background:#14243b;color:white}h1{margin:0 0 10px;font-size:26px}p{line-height:1.5}main{max-width:1600px;margin:24px auto;padding:0 16px}section{background:white;margin-bottom:24px;border-radius:12px;overflow:auto;box-shadow:0 2px 12px #12203812}svg{width:100%;height:auto;min-width:950px;display:block}.note{padding:0 20px 12px;color:#536176}@media print{header{background:white;color:black}section{break-after:page;box-shadow:none}svg{min-width:0}}</style><header><h1>Data observability · Release 1 design</h1><p>View offline in any modern browser. Scroll horizontally on a small screen, or use browser zoom. Two editable pages are in the companion .drawio file.</p><p>Edit: open app.diagrams.net → File → Open From → Device → release1_architecture.drawio. Export SVG after edits. The SVG files also embed the diagram source.</p></header><main>'''
for data in svgs:html+='<section>'+data+'</section>'
html+='<p class="note">Design only. The availability page shows the production target. See ../release1_design.md for contracts, capability limits, security and release gates.</p></main></html>'
(OUT/'release1_viewer.html').write_text(html)
print(json.dumps({'pages':len(pages),'nodes':[len(p['nodes']) for p in pages],'edges':[len(p['edges']) for p in pages]}))
