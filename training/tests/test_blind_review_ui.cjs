/* Node-only DOM harness: validates script behavior, not browser rendering. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const template = fs.readFileSync(path.join(__dirname,'../templates/blind_review.html'),'utf8');
const fixture = {version:1,packet_id:'qa-only',items:Array.from({length:22},(_,n)=>({
  id:`R${String(n+1).padStart(2,'0')}`,category:'반말',register:'반말',
  turns:[{question:'질문',A:'<img src=x onerror=alert(1)>',B:'응답'}]
}))};
const html = process.argv[2] ? fs.readFileSync(process.argv[2],'utf8') : template.replace('__PACKET_JSON__',JSON.stringify(fixture));
const packet = JSON.parse(html.match(/<script id="packet" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
function environment(storageFails=false, prior=null){
  const nodes={},all=[],stored={},downloads=[],blobs=[];
  class Element{
    constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.value='';this.attrs={};all.push(this);}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    setAttribute(k,v){this.attrs[k]=v;}
    addEventListener(type,fn){this.listeners[type]=fn;}
    click(){if(this.tag==='a')downloads.push(this);if(this.listeners.click)return this.listeners.click({target:this});}
    remove(){}
  }
  for(const id of ['packet','status','progress','cards','export','import','print'])nodes[id]=new Element('div');
  nodes.packet.textContent=JSON.stringify(packet);
  let allowed=true;
  const context={document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),body:new Element('body')},
    localStorage:{getItem:k=>{if(storageFails)throw Error();return prior||stored[k]||null;},setItem:(k,v)=>{if(storageFails)throw Error();stored[k]=v;}},
    Blob:class{constructor(parts){this.text=parts.join('');blobs.push(this);}},
    URL:{createObjectURL:()=> 'blob:qa-only',revokeObjectURL(){}},
    confirm:()=>allowed,setTimeout:fn=>fn(),window:{print(){}},console};
  vm.createContext(context);vm.runInContext(script,context);
  return {context,nodes,all,stored,downloads,blobs,cancel:()=>{allowed=false;}};
}
const clone = value => JSON.parse(JSON.stringify(value));

test('all responses render as text; grades start empty with no model metadata',()=>{
  const e=environment();
  assert.equal(e.nodes.cards.children.length,packet.items.length);
  assert.equal(e.all.filter(n=>n.className==='spoken').length,packet.items.reduce((n,i)=>n+i.turns.length*2,0));
  assert.equal(e.nodes.progress.textContent,'판정 0/22 · 보류 0 · 미판정 22');
  const value=clone(e.context.reviewCore.blank());
  assert.ok(Object.values(value.ratings).every(r=>r.preference===null&&Object.values(r.A).every(n=>n===null)&&Object.values(r.B).every(n=>n===null)));
  assert.equal(script.includes('innerHTML'),false);
});
test('reject wrong packet, missing or unknown card, invalid score and malformed import',()=>{
  const e=environment(),core=e.context.reviewCore,good=clone(core.blank());
  for(const mutate of [v=>v.packet_id='wrong',v=>delete v.ratings.R01,v=>v.ratings.UNKNOWN=v.ratings.R01,
      v=>v.ratings.R01.A.content=0,v=>v.ratings.R01.B.criterion=6,v=>v.ratings.R01.A.content=2.5,
      v=>v.ratings.R01.A.content='3',v=>v.ratings.R01.preference='winner',v=>v.ratings.R01.comment='a'.repeat(4001)]){
    const input=clone(good);mutate(input);assert.throws(()=>core.validate(input));
  }
  assert.deepEqual(clone(core.validate(good)),good);
});
test('hold, untouched and decided are distinct; scores alone do not imply a winner',()=>{
  const e=environment(),core=e.context.reviewCore,v=clone(core.blank());
  v.ratings.R01.preference='hold';v.ratings.R02.preference='both_bad';v.ratings.R03.A.naturalness=5;
  assert.deepEqual(clone(core.counts(v)),{decided:1,hold:1,untouched:20});
});
test('form changes autosave, reload restores, export/import round trips partially completed ratings',async()=>{
  const e=environment();
  const pref=e.all.find(n=>n.attrs['aria-label']==='R01 선호');pref.value='B';pref.listeners.change();
  const score=e.all.find(n=>n.attrs['aria-label']==='R01 A content');score.value='4';score.listeners.change();
  const note=e.all.find(n=>n.attrs['aria-label']==='R01 메모');note.value='QA 임시 입력';note.listeners.input();
  e.nodes.export.click();const exported=JSON.parse(e.blobs[0].text);
  assert.equal(e.downloads.length,1);assert.equal(exported.all_cards_decided,false);
  assert.deepEqual(exported.progress,{decided:1,hold:0,untouched:21});
  assert.equal(exported.ratings.R01.B.content,null);
  const saved=Object.values(e.stored)[0],again=environment(false,saved);
  assert.equal(again.all.find(n=>n.attrs['aria-label']==='R01 선호').value,'B');
  const fresh=environment(),input=fresh.nodes.import;
  input.files=[{size:e.blobs[0].text.length,text:async()=>e.blobs[0].text}];
  await input.listeners.change({target:input});fresh.nodes.export.click();
  assert.deepEqual(JSON.parse(fresh.blobs[0].text).ratings,exported.ratings);
});
test('failed/cancelled import preserves current data; blocked storage permits file export',async()=>{
  const e=environment(true),input=e.nodes.import;
  input.files=[{size:5,text:async()=>'{bad'}];await input.listeners.change({target:input});
  assert.match(e.nodes.status.textContent,/불러오기 실패/);
  e.nodes.export.click();assert.equal(JSON.parse(e.blobs[0].text).progress.decided,0);
  const grades=clone(e.context.reviewCore.blank());grades.ratings.R01.preference='A';
  input.files=[{size:100,text:async()=>JSON.stringify(grades)}];e.cancel();await input.listeners.change({target:input});
  e.nodes.export.click();assert.equal(JSON.parse(e.blobs[1].text).progress.decided,0);
});
