async (page) => {
 const j=page.__hardLoad;if(!j.done)return {error:'Main run still active'};
 const cases=[{"id":"s08","question":"Ba bạn: A có ĐTBCHK 3,65 và ĐRL 91; B có ĐTBCHK 3,9 và ĐRL 88; C có ĐTBCHK 3,3 và ĐRL 80. Xếp thứ tự ưu tiên xét học bổng giúp mình."},{"id":"b08","question":"ĐTBCTL của mình là 3,0 với 90 TC tích lũy. Mình học cải thiện một môn 3 TC từ điểm C lên điểm A thì ĐTBCTL mới là bao nhiêu?"},{"id":"s04","question":"ĐTBCHK của mình là 3,3 còn ĐRL là 79 thì mình thuộc mức học bổng nào?"},{"id":"w11","question":"Mình đã bị cảnh báo học tập, học kỳ kế tiếp ĐTBCHK của mình đúng 1,00. Mình có bị buộc thôi học không?"},{"id":"s05","question":"Bạn A có ĐTBCHK 3,5 và ĐRL 88, bạn B có ĐTBCHK 3,5 và ĐRL 84, cả hai đều đủ điều kiện. Ai được ưu tiên học bổng?"},{"id":"k08","question":"Chương trình 120 TC, mình mới học 20 TC với ĐTBCTL 4,0. Mình có thể đạt loại xuất sắc không, cần điểm trung bình bao nhiêu ở phần còn lại?"}];
 j.rechecks=[];j.rechecksDone=false;j.phase='rechecking after cooldown';
 const ws=[0,1].map(i=>j.workers.find(w=>w.index===i));
 async function run(w,assigned){
  for(const c of assigned){
   const label='recheck_'+c.id;
   try{
    const dismiss=w.tab.getByRole('button',{name:'Mình hiểu rồi',exact:true});
    if(await dismiss.isVisible().catch(()=>false))await dismiss.click();
    await w.tab.getByRole('button',{name:'Cuộc trò chuyện mới',exact:true}).click();
    await w.tab.evaluate(id=>window.__loadCase=id,label);
    await w.tab.getByRole('textbox',{name:'Câu hỏi của bạn'}).fill(c.question);
    await w.tab.getByRole('button',{name:'Gửi',exact:true}).click();
    await w.tab.waitForFunction(id=>window.__loadMetrics.some(m=>m.caseId===id&&m.ended),label,{timeout:180000});
    const m=await w.tab.evaluate(id=>window.__loadMetrics.find(m=>m.caseId===id),label);
    const r={...m,baseCaseId:c.id,worker:w.index};
    if(m.doneS!=null){await w.tab.getByRole('button',{name:'Báo câu trả lời sai',exact:true}).waitFor({state:'visible',timeout:5000});r.uiCompleted=true;}
    j.rechecks.push(r);
    if(m.error==='LLM_RATE_LIMITED'&&m.retryAfter>0&&m.retryAfter<=60)await new Promise(resolve=>setTimeout(resolve,m.retryAfter*1000+500));
   }catch(e){j.rechecks.push({caseId:label,baseCaseId:c.id,error:e.name,message:String(e.message).slice(0,150)});break;}
  }
 }
 j.recheckPromise=Promise.all(ws.map((w,i)=>run(w,cases.filter((_,idx)=>idx%2===i)))).finally(()=>{j.rechecksDone=true;j.rechecksFinishedAt=new Date().toISOString();j.phase='finished';});
 return {started:true,cases:cases.map(c=>c.id),users:2,payload:'Original Vietnamese question only; no supplemental suffix'};
}
