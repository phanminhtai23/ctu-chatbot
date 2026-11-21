async (page) => {
 const j=page.__stepJob={startedAt:new Date().toISOString(),results:[],done:false,question:"Chương trình 151 TC, mình đã học 100 TC với ĐTBCTL 3,5. Trong 100 TC đó có 30 TC điều kiện và tổng TC điều kiện của chương trình cũng là 30. Còn bao nhiêu TC phải học, và để đạt xuất sắc thì cần điểm trung bình bao nhiêu ở phần còn lại?"};
 function instrument(){
  window.__steps=[];window.__stepLabel='';
  document.addEventListener('click',e=>{if(e.target.closest?.('button')?.getAttribute('aria-label')==='Gửi')window.__nativeSend=performance.now();},true);
  const original=window.fetch.bind(window);
  window.fetch=async(input,init)=>{
   const url=String(input instanceof Request?input.url:input);
   if(!url.includes('/messages/stream'))return original(input,init);
   const start=performance.now(),click=window.__nativeSend||start;
   const m={label:window.__stepLabel,startedAt:new Date().toISOString(),feBeforeStreamS:(start-click)/1000,ttftS:null,doneS:null,queued:[],_click:click};
   window.__steps.push(m);
   const headers=new Headers(init?.headers||(input instanceof Request?input.headers:undefined));headers.set('X-Step-Run',m.label);
   try{
    const response=await original(input,{...init,headers});m.status=response.status;m.headersS=(performance.now()-click)/1000;
    (async()=>{try{
     if(!response.ok){m.error='HTTP_'+response.status;m.ended=true;return;}
     const reader=response.clone().body.getReader(),decoder=new TextDecoder();let pending='';
     while(true){const part=await reader.read();if(part.done)break;pending+=decoder.decode(part.value,{stream:true});let split;
      while((split=pending.indexOf('\n\n'))>=0){const block=pending.slice(0,split);pending=pending.slice(split+2);let event='',data={};
       for(const line of block.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:')){try{data=JSON.parse(line.slice(5));}catch{}}}
       const seconds=(performance.now()-click)/1000;
       if(event==='token'&&data.text&&m.ttftS===null)m.ttftS=seconds;
       if(event==='queued')m.queued.push({position:data.position,seconds});
       if(event==='done'){m.doneS=seconds;m.cached=data.assistant_message?.cached;m.answer=data.assistant_message?.content;m.sources=data.assistant_message?.sources;m.serverDurationS=data.assistant_message?.duration_seconds;}
       if(event==='error'){m.error=data.code;m.errorS=seconds;}
      }
     }m.endedS=(performance.now()-click)/1000;m.ended=true;
    }catch(e){m.error=e.name;m.ended=true;}})();
    return response;
   }catch(e){m.error=e.name;m.ended=true;throw e;}
  };
  new MutationObserver(()=>{
   const m=window.__steps.at(-1);if(!m||m.label!==window.__stepLabel)return;
   const bubbles=Array.from(document.querySelectorAll('[role="log"] .group.items-start'));
   const bubble=bubbles.at(-1);if(!bubble)return;
   const content=bubble.firstElementChild;
   if(!m.uiFirstS&&content?.textContent?.trim()&&!content.querySelector('[role="status"]'))m.uiFirstS=(performance.now()-m._click)/1000;
   if(!m.uiDoneS&&Array.from(bubble.querySelectorAll('button')).some(b=>b.textContent.includes('Báo câu trả lời sai')))m.uiDoneS=(performance.now()-m._click)/1000;
  }).observe(document,{subtree:true,childList:true,characterData:true});
 }
 const context=await page.context().browser().newContext({viewport:{width:1280,height:850}});
 j.context=context;j.tab=await context.newPage();await context.addInitScript(instrument);
 j.promise=(async()=>{
  try{
   await j.tab.goto('http://host.docker.internal:5173/login',{waitUntil:'domcontentloaded'});
   await j.tab.getByRole('textbox',{name:'Email sinh viên'}).fill('step-profile-20261121@student.edu.ctu.vn');
   await j.tab.getByRole('button',{name:'Đăng nhập',exact:true}).click();await j.tab.waitForURL('**/chat');
   try{await j.tab.getByRole('button',{name:'Gét gô!',exact:true}).click({timeout:2000});}catch{}
   for(let i=1;i<=5;i++){
    const dismiss=j.tab.getByRole('button',{name:'Mình hiểu rồi',exact:true});if(await dismiss.isVisible().catch(()=>false))await dismiss.click();
    await j.tab.getByRole('button',{name:'Cuộc trò chuyện mới',exact:true}).click();
    await j.tab.evaluate(label=>window.__stepLabel=label,'step_'+i);
    await j.tab.getByRole('textbox',{name:'Câu hỏi của bạn'}).fill(j.question);
    await j.tab.getByRole('button',{name:'Gửi',exact:true}).click();
    await j.tab.waitForFunction(label=>window.__steps.some(m=>m.label===label&&m.ended&&(m.uiDoneS!=null||m.error)),'step_'+i,{timeout:180000});
    const m=await j.tab.evaluate(label=>{const m=window.__steps.find(m=>m.label===label);const {_click,...safe}=m;return safe;},'step_'+i);
    j.results.push(m);
   }
  }catch(e){j.error=e.name+': '+String(e.message).slice(0,200);}
  finally{j.done=true;j.finishedAt=new Date().toISOString();}
 })();
 return {started:true,runs:5,question:j.question};
}
