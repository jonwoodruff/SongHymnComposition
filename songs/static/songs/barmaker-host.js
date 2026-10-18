// This small adapter is the only place BarMaker knows about the host's editor.
document.querySelectorAll('.bar-maker-panel').forEach(panel=>{
  const maker=panel.querySelector('bar-maker'),form=panel.closest('.part-editor');
  const field=form.querySelector('textarea[name=content]'),status=panel.querySelector('.snippet-status');
  panel.querySelector('.append-snippet').onclick=()=>{
    if(field.readOnly){status.textContent='The tune is currently being edited or reviewed elsewhere. Your snippet is kept here.';return;}
    if(maker.state!=='idle'){status.textContent='Stop your performance or playback first.';return;}
    const snippet=maker.getABC();
    if(!snippet.trim()){status.textContent='Create a snippet first.';return;}
    const current=field.value.trim();
    const hasNotes=Boolean(window.BarMaker.abcBody(current));
    const next=hasNotes?`${current}\n${maker.getInsertableABC()}\n`:snippet;
    field.value=next;field.dispatchEvent(new Event('input',{bubbles:true}));
    status.textContent='Snippet appended. The tune will save automatically.';
  };
  form.closest('.section-editor').addEventListener('toggle',event=>{if(event.target===event.currentTarget&&!event.target.open)maker.cancel();});
  window.addEventListener('playback:recording',()=>{if(maker.state==='playing')maker.stop();});
});
window.addEventListener('beforeunload',event=>{
  if([...document.querySelectorAll('bar-maker')].some(maker=>maker.state&&maker.state!=='idle')){event.preventDefault();event.returnValue='';}
});
