// Optional DOM integration check: install jsdom separately, then set NODE_PATH.
// This checks UI behavior, not browser rendering or responsive layout.
const {JSDOM,VirtualConsole}=require('jsdom');
const fs=require('fs');
const base=process.env.SMOKE_BASE;
const key=fs.readFileSync('.env','utf8').split('\n').find(x=>x.startsWith('SKYLINEE_API_KEY=')).split('=')[1];
(async()=>{
  const errors=[];
  const vc=new VirtualConsole();
  vc.on('jsdomError',e=>errors.push(e.message));
  const dom=await JSDOM.fromURL(base,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(window){window.fetch=(url,options)=>fetch(new URL(url,base),options)}});
  const w=dom.window,d=w.document,$=id=>d.getElementById(id);
  async function until(fn,label){const end=Date.now()+15000;while(Date.now()<end){if(fn())return;await new Promise(r=>setTimeout(r,40))}throw Error('Timed out: '+label+'; notice: '+$('notice').textContent)}
  function submit(id){$(id).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}))}
  try{
    await until(()=>$('connect').onclick,'script load');
    $('key').value=key;$('connect').click();
    await until(()=>$('connection').textContent.includes('Connected'),'connect');
    $('doctor').click();await until(()=>$('diagnostics').textContent.includes('"demo_backend": true'),'doctor');
    $('prompt').value='calculate demo';submit('prompt-form');
    await until(()=>$('run-status').textContent==='COMPLETED','calculator');
    if(!$('conversation').textContent.includes('42'))throw Error('Missing calculator result');
    $('prompt').value='write demo report';submit('prompt-form');
    await until(()=>$('run-status').textContent==='WAITING APPROVAL','write proposal');
    const approve=()=>[...$('approval-list').querySelectorAll('button')].find(x=>x.textContent==='Approve exact action');
    await until(()=>approve(),'approval display');approve().click();
    await until(()=>$('run-status').textContent==='COMPLETED','approved write');
    $('memory-text').value='Dashboard smoke memory';submit('memory-form');
    await until(()=>$('memories').textContent.includes('Dashboard smoke memory'),'memory save');
    $('skill-name').value='dom-review';$('skill-content').value='Inspect evidence, then summarize.';submit('skill-form');
    await until(()=>$('skills').textContent.includes('dom-review'),'skill save');
    $('schedule-name').value='DOM daily';$('schedule-prompt').value='calculate demo';submit('schedule-form');
    await until(()=>$('schedules').textContent.includes('DOM daily'),'schedule create');
    [...$('schedules').querySelectorAll('button')].find(x=>x.textContent==='Delete schedule').click();
    await until(()=>$('schedules').textContent==='No scheduled tasks.','schedule delete');
    d.querySelector('[data-view="approvals"]').click();
    if($('approvals').hidden||!$('work').hidden)throw Error('Tab switch failed');
    if(errors.length)throw Error(errors.join('\n'));
    console.log('Dashboard DOM workflow passed: connect, doctor, tool loop, approval, memory, skills, schedule create/delete, tabs.');
  }finally{w.close()}
})().catch(e=>{console.error(e);process.exit(1)});
