const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const runtimeModules = '/Users/sanaiqbal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
function load(name) {
  try { return require(name); }
  catch (error) {
    if (error.code !== 'MODULE_NOT_FOUND') throw error;
    return require(path.join(runtimeModules, name));
  }
}
const sharp = load('sharp');
const { createCanvas } = load('@napi-rs/canvas');
const measure = createCanvas(1, 1).getContext('2d');
const C = {
  ink: '#17333d', muted: '#4d6771', line: '#527684', rule: '#d7e2e6',
  gray: ['#f3f7f8', '#a1b6bf', '#365761'],
  teal: ['#e6f4ee', '#72ad99', '#1f6d58'],
  blue: ['#e8f0fb', '#8aa8cf', '#315e91'],
  gold: ['#fff4d7', '#c8a04a', '#896014'],
  queue: ['#f8ecdf', '#c89c6b', '#8a5e30'],
};
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');

class Diagram {
  constructor(width, height, title, subtitle) {
    this.width = width; this.height = height; this.parts = []; this.boxes = []; this.routes = [];
    this.text(80,75,title,{size:46,weight:700,anchor:'start',width:width-160});
    this.text(80,120,subtitle,{size:25,anchor:'start',width:width-160,color:C.muted});
    this.parts.push(`<path d="M80 148 H${width-80}" stroke="${C.rule}" stroke-width="2"/>`);
  }
  text(x,y,content,options={}) {
    const {size=25,weight=400,anchor='middle',width=500,color=C.ink}=options;
    const lines=[];
    measure.font=`${weight} ${size}px Arial`;
    for(const paragraph of String(content).split('\n')) {
      let line='';
      for(const word of paragraph.split(' ')) {
        const candidate=line?`${line} ${word}`:word;
        if(measure.measureText(candidate).width>width && line) {lines.push(line);line=word;}
        else line=candidate;
      }
      lines.push(line);
    }
    for(let i=0;i<lines.length;i++) {
      assert(measure.measureText(lines[i]).width<=width+1,`Text too wide: ${lines[i]}`);
      this.parts.push(`<text x="${x}" y="${y+i*(size+9)}" text-anchor="${anchor}" font-family="Arial, Helvetica, sans-serif" font-size="${size}" font-weight="${weight}" fill="${color}">${escape(lines[i])}</text>`);
    }
    return y+(lines.length-1)*(size+9)+size*0.25;
  }
  band(y,height,title,fill='#f8fafb') {
    this.parts.push(`<rect x="48" y="${y}" width="${this.width-96}" height="${height}" rx="8" fill="${fill}"/>`);
    this.text(80,y+33,title,{size:21,weight:700,anchor:'start',width:this.width-160,color:C.muted});
  }
  box(id,x,y,width,height,tag,title,body,kind='gray') {
    const [fill,stroke,accent]=C[kind];
    this.boxes.push({id,x,y,width,height});
    this.parts.push(`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`);
    if(tag)this.text(x+width/2,y+31,tag,{size:19,weight:700,width:width-32,color:accent});
    this.text(x+width/2,y+72,title,{size:29,weight:700,width:width-36});
    if(body) {
      const bottom=this.text(x+width/2,y+110,body,{size:23,width:width-36,color:C.muted});
      assert(bottom<y+height-11,`Text exceeds ${id}`);
    }
  }
  diamond(id,cx,cy,width,height,title,body) {
    this.boxes.push({id,x:cx-width/2,y:cy-height/2,width,height,diamond:true});
    this.parts.push(`<polygon points="${cx},${cy-height/2} ${cx+width/2},${cy} ${cx},${cy+height/2} ${cx-width/2},${cy}" fill="${C.gold[0]}" stroke="${C.gold[1]}" stroke-width="2"/>`);
    this.text(cx,cy-10,title,{size:27,weight:700,width:width*0.6});
    this.text(cx,cy+28,body,{size:22,width:width*0.58,color:C.gold[2]});
  }
  arrow(points,label='',at=null,{dashed=false,color=C.line,head=true}={}) {
    for(let i=1;i<points.length;i++) {
      const [x1,y1]=points[i-1],[x2,y2]=points[i];
      assert(x1===x2||y1===y2,'Connectors must be orthogonal');
    }
    this.routes.push(points);
    const d=points.map(([x,y],i)=>`${i?'L':'M'}${x},${y}`).join(' ');
    this.parts.push(`<path d="${d}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" ${dashed?'stroke-dasharray="9 7"':''} ${head?'marker-end="url(#arrow)"':''}/>`);
    if(label&&at)this.text(at[0],at[1],label,{size:22,width:at[2]||500,color:C.muted});
  }
  junction(x,y){this.parts.push(`<circle cx="${x}" cy="${y}" r="5" fill="${C.line}"/>`);}
  verify() {
    for(let i=0;i<this.boxes.length;i++) {
      const a=this.boxes[i];
      assert(a.x>=0&&a.y>=0&&a.x+a.width<=this.width&&a.y+a.height<=this.height,`Out-of-canvas: ${a.id}`);
      for(let j=i+1;j<this.boxes.length;j++) {
        const b=this.boxes[j];
        assert(!(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y),`Overlapping nodes: ${a.id}, ${b.id}`);
      }
    }
    for(const points of this.routes)for(let i=1;i<points.length;i++) {
      const [x1,y1]=points[i-1],[x2,y2]=points[i];
      for(const b of this.boxes) {
        if(b.diamond)continue;
        const p=1;
        const crosses=x1===x2
          ?x1>b.x+p&&x1<b.x+b.width-p&&Math.max(y1,y2)>b.y+p&&Math.min(y1,y2)<b.y+b.height-p
          :y1>b.y+p&&y1<b.y+b.height-p&&Math.max(x1,x2)>b.x+p&&Math.min(x1,x2)<b.x+b.width-p;
        assert(!crosses,`Connector crosses node: ${b.id}`);
      }
    }
  }
  svg() {
    this.verify();
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${this.width}" height="${this.height}" viewBox="0 0 ${this.width} ${this.height}"><defs><marker id="arrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse"><path d="M1 1 L10 6 L1 11 Z" fill="${C.line}"/></marker></defs><rect width="100%" height="100%" fill="white"/>${this.parts.join('')}</svg>`;
  }
}

function architecture() {
  const d=new Diagram(2560,1540,'Workflow Platform Architecture','Existing API and transport paths dispatch one workflow; ADK owns the internal nodes and edges.');
  d.band(180,240,'01  REQUEST AND PLANNING');
  d.box('request',80,240,350,150,'CLIENT','Send request','Task or conversation');
  d.box('api',530,240,450,150,'ORCHESTRATOR','Validate request','Identity + configuration');
  d.box('plan',1080,240,540,150,'ORCHESTRATOR','Create outer plan','Select agent or workflow version','teal');
  d.box('mode',1720,240,740,150,'ORCHESTRATOR','Choose execution path','ASYNC, SYNC or HYBRID','teal');
  d.arrow([[430,315],[530,315]]);d.arrow([[980,315],[1080,315]]);d.arrow([[1620,315],[1720,315]]);
  d.band(510,250,'02  TRANSPORT');
  d.box('http',800,575,600,150,'DIRECT HTTP','Sync coordinator','SYNC + background HYBRID','blue');
  d.box('kafka',1600,575,600,150,'KAFKA','Queued execution','ASYNC dispatch','queue');
  d.arrow([[2090,390],[2090,465],[1100,465],[1100,575]],'SYNC / HYBRID',[1210,448,400]);
  d.arrow([[1900,465],[1900,575]],'ASYNC',[2010,535,220]);d.junction(1900,465);
  d.band(875,300,'03  EXECUTION');
  d.box('entry',80,950,440,180,'EXECUTOR','Resolve executable','Load pinned definition\nCompile native workflow');
  d.box('native',620,950,660,180,'NATIVE ADK RUNTIME','Execute workflow','Agentic + deterministic + decision nodes\nADK follows the configured edges','blue');
  d.box('response',1380,950,520,180,'ORCHESTRATOR','Build final response','Use the root workflow output\nAdvance the outer step once','teal');
  d.box('delivery',2000,950,460,180,'CLIENT DELIVERY','Receive result','HTTP, configured result channel\nor connected SSE');
  d.arrow([[1100,725],[1100,800],[300,800],[300,855]],'',null,{head:false});
  d.arrow([[1900,725],[1900,855],[300,855]],'Common Executor execution adapter',[1260,836,650],{head:false});
  d.junction(300,855);d.arrow([[300,855],[300,950]]);
  d.arrow([[520,1040],[620,1040]]);d.arrow([[1280,1040],[1380,1040]]);d.arrow([[1900,1040],[2000,1040]]);
  d.band(1230,235,'04  PERSISTENCE','#ffffff');
  d.box('definitions',80,1300,440,140,'VERSIONED CONFIG','Workflow definitions','Nodes, edges and dependencies');
  d.box('sessions',620,1300,660,140,'EXECUTOR PERSISTENCE','ADK sessions and checkpoints','Saved native execution state');
  d.box('runtime',1380,1300,520,140,'ORCHESTRATOR PERSISTENCE','Task runtime and results','Outer plan, status and run references');
  d.arrow([[300,1300],[300,1130]],'Load',[400,1210,190],{dashed:true});
  d.arrow([[950,1130],[950,1300]],'Checkpoint',[1070,1210,220],{dashed:true});
  d.arrow([[1640,1130],[1640,1300]],'Persist status',[1770,1210,240],{dashed:true});
  d.text(2230,1330,'Solid arrows: execution / delivery',{size:22,width:450,color:C.muted});
  d.text(2230,1375,'Dashed arrows: persistence access',{size:22,width:450,color:C.muted});
  return d;
}
function example() {
  const d=new Diagram(2800,1490,'Mixed Workflow | Agent Followed by Exact Data Composition','The agent writes the explanation. Application code preserves the original tool block and adds it at final delivery.');
  d.band(180,340,'01  WORKFLOW INSIDE THE EXECUTOR');
  d.box('request',80,260,340,190,'INPUT','Request','Get a report\nand show the results');
  d.box('fetch',520,260,500,190,'DETERMINISTIC NODE','Fetch tool data','Store the original output\nReturn status + row count','teal');
  d.box('agent',1160,260,500,190,'AGENTIC NODE','Write explanation','Uses the question and small facts\nOriginal rows are not provided','blue');
  d.box('compose',1800,260,660,190,'DETERMINISTIC NODE','Append-original response step','Choose layout and bind the original output\nEmit a small response manifest','teal');
  d.arrow([[420,355],[520,355]]);
  d.arrow([[1020,355],[1160,355]],'Safe facts',[1090,327,130]);
  d.arrow([[1660,355],[1800,355]]);
  d.band(690,340,'02  SEPARATE DATA AND PRESENTATION PATHS');
  d.box('original',520,760,500,200,'SERVER-SIDE ORIGINAL OUTPUT','Preserve tool bytes','Original block + checksum\nNot model-visible session data','gray');
  d.box('manifest',1800,760,660,200,'RESPONSE MANIFEST','Explanation + original reference','The private reference identifies the data\nThe graph does not copy raw rows into output','gray');
  d.arrow([[770,450],[770,760]],'Original tool data',[960,620,310],{dashed:true});
  d.arrow([[2130,450],[2130,760]],'Explanation + reference',[2420,620,480]);
  d.arrow([[1020,860],[1800,860]],'Server-only reference',[1410,837,650],{dashed:true});
  d.band(1120,320,'03  FINAL DELIVERY AFTER ALL MODEL STAGES');
  d.box('finalize',1800,1180,660,200,'ORCHESTRATOR / DELIVERY','Assemble and send response','Explanation + unchanged original tool data\nCopy the original block without model rewriting','teal');
  d.box('client',2540,1190,180,180,'','Client','Final\nresponse');
  d.arrow([[2130,960],[2130,1180]],'Apply deterministic finalizer',[2420,1080,520]);
  d.arrow([[770,960],[770,1280],[1800,1280]],'Load and verify original bytes',[1285,1253,790],{dashed:true});
  d.arrow([[2460,1280],[2540,1280]]);
  d.text(420,1390,'Private output-store adapter must be durable across workers and restarts.',{size:22,width:760,color:C.muted});
  return d;
}
function visualBuilder() {
  const d=new Diagram(2800,1440,'Visual Workflow Builder | From Canvas to ADK Execution','Users connect registered capabilities. The backend validates and compiles the saved definition into a native workflow.');
  d.band(180,340,'01  WORKFLOW AUTHORING');
  d.box('palette',80,260,540,190,'NODE CATALOGUE','Pick a capability','Registered tool, function, agent,\ndecision or response composer','gray');
  d.box('canvas',760,260,600,190,'CANVAS','Drop nodes and connect edges','Choose the order of operations\nLabel decision routes','blue');
  d.box('properties',1500,260,600,190,'PROPERTIES','Map typed inputs and outputs','Choose agent/tool settings\nKeep original data server-only','teal');
  d.box('save',2240,260,480,190,'DRAFT','Save the design','Graph + data bindings\nLayout saved separately','gray');
  d.arrow([[620,355],[760,355]]);d.arrow([[1360,355],[1500,355]]);d.arrow([[2100,355],[2240,355]]);
  d.box('definition',1000,700,600,180,'SAVED APPLICATION DEFINITION','Versioned graph JSON','Executable IDs, edges and bindings','gray');
  d.box('publish',2240,700,480,180,'SERVER VALIDATION','Validate and publish','Check schemas and permitted nodes\nFreeze version + dependencies','teal');
  d.arrow([[2480,450],[2480,600],[1300,600],[1300,700]],'Saved design, not executable browser code',[1870,578,900]);
  d.arrow([[1600,790],[2240,790]],'Validate / test / publish',[1920,767,550]);
  d.band(1090,280,'02  EXECUTION');
  d.box('api',80,1160,700,190,'EXISTING ORCHESTRATOR API','Select workflow for the request','Use-case configuration selects a published version\nKeep SYNC / ASYNC / HYBRID transport','gray');
  d.box('compiler',950,1160,740,190,'EXECUTOR COMPILER','Build native ADK nodes and edges','Resolve registered implementations and data bindings\nADK owns internal traversal','blue');
  d.box('execute',1810,1160,910,190,'NATIVE WORKFLOW + FINAL DELIVERY','Tool -> Agent -> Deterministic Composer','Run the graph and apply its final response policy\nDeliver explanation plus the unchanged original data','teal');
  d.arrow([[2480,880],[2480,1000],[430,1000],[430,1160]],'Normal task requests select a published version',[1620,977,1500]);
  d.arrow([[780,1255],[950,1255]]);d.arrow([[1690,1255],[1810,1255]]);
  return d;
}
function modes() {
  const d=new Diagram(2560,1710,'Execution Modes | One Workflow Runtime','Read each column from top to bottom. Transport changes; the native ADK workflow stays the same.');
  const columns=[
    {x:80,name:'SYNC',desc:'The client waits for completion',kind:'blue',steps:[
      ['CLIENT','Submit request','Call the sync task API'],
      ['ORCHESTRATOR','Validate and create plan','Save the outer runtime'],
      ['DIRECT HTTP','Dispatch executable','Sync coordinator calls Executor'],
      ['EXECUTOR','Run native ADK workflow','Nodes and edges execute internally'],
      ['ORCHESTRATOR -> CLIENT','Return final response','Complete the original HTTP request'],
    ]},
    {x:910,name:'ASYNC / KAFKA',desc:'The client receives a result later',kind:'queue',steps:[
      ['CLIENT','Submit request','Call the async task API'],
      ['ORCHESTRATOR','Validate, plan and acknowledge','Persist accepted work before dispatch'],
      ['KAFKA','Deliver work to a consumer','Deduplicate and acquire run ownership'],
      ['EXECUTOR','Run native ADK workflow','Nodes and edges execute internally'],
      ['KAFKA -> ORCHESTRATOR','Deliver persisted root outcome','Build response and deliver to client'],
    ]},
    {x:1740,name:'HYBRID',desc:'Early acknowledgement, background execution',kind:'teal',steps:[
      ['CLIENT','Submit request','Select a HYBRID-configured use case'],
      ['ORCHESTRATOR','Validate, plan and acknowledge','Persist accepted background work'],
      ['BACKGROUND DIRECT HTTP','Dispatch executable','Background coordinator calls Executor'],
      ['EXECUTOR','Run native ADK workflow','Nodes and edges execute internally'],
      ['ORCHESTRATOR -> CLIENT','Deliver final response','Use the configured delivery channel'],
    ]},
  ];
  for(const col of columns) {
    const [fill,stroke,accent]=C[col.kind];
    d.parts.push(`<rect x="${col.x}" y="185" width="740" height="1230" rx="8" fill="#fbfcfd" stroke="${stroke}" stroke-width="2"/>`);
    d.parts.push(`<rect x="${col.x}" y="185" width="740" height="110" rx="8" fill="${fill}"/>`);
    d.text(col.x+370,231,col.name,{size:30,weight:700,width:680,color:accent});
    d.text(col.x+370,269,col.desc,{size:22,width:690,color:C.muted});
    for(let i=0;i<col.steps.length;i++) {
      const y=330+i*215,[tag,title,body]=col.steps[i];
      d.box(`${col.name}-${i}`,col.x+40,y,660,150,tag,title,body,i===3?'blue':col.kind);
      if(i<col.steps.length-1)d.arrow([[col.x+370,y+150],[col.x+370,y+215]]);
    }
  }
  d.box('sse',80,1480,2400,160,'OPTIONAL DELIVERY STYLE','STREAM / SSE','Send selected progress events while the configured mode executes. Streaming does not create a fourth execution mode.','gray');
  return d;
}
async function main() {
  const items=[['01-platform-architecture',architecture()],['02-example-workflow',example()],['03-execution-modes',modes()],['04-visual-builder',visualBuilder()]];
  for(const [name,diagram]of items) {
    const svg=diagram.svg();
    fs.writeFileSync(path.join(__dirname,`${name}.svg`),svg);
    const target=path.join(__dirname,`${name}.png`);
    await sharp(Buffer.from(svg)).png().toFile(target);
    const stats=await sharp(target).stats();
    assert(stats.channels.some(channel=>channel.stdev>15),'Diagram is blank');
    process.stdout.write(`${name}: ${diagram.width} x ${diagram.height}; ${diagram.boxes.length} nodes; orthogonal routes and no node crossings\n`);
  }
}
main().catch(error=>{process.stderr.write(`${error.stack}\n`);process.exitCode=1;});
