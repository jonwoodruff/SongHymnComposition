/* A small, single-voice editor. abcjs renders notation; Web Audio previews it. */
(() => {
  const initial = 'X:1\nM:4/4\nL:1/4\nK:C\n';
  let audio;
  function play(abc) {
    if (audio) audio.close();
    audio = new (window.AudioContext || window.webkitAudioContext)();
    audio.resume();
    const unit = Number((abc.match(/^Q:1\/4=(\d+)/m)||[])[1] || 100);
    const body = abc.split('\n').filter(l=>!/^\w:/.test(l)).join(' ');
    const notes = [...body.matchAll(/([A-Ga-gz])([,']?)(\d*(?:\/\d*)?)/g)];
    let start = audio.currentTime + .1;
    notes.forEach(match => {
      let duration = 1;
      if (match[3].includes('/')) { const [a,b] = match[3].split('/'); duration = Number(a||1)/Number(b||2); }
      else duration = Number(match[3]||1);
      duration = Math.min(8,Math.max(.125,duration)) * 60/unit;
      if (match[1] !== 'z') {
        const semis = {C:0,D:2,E:4,F:5,G:7,A:9,B:11};
        const midi=60+semis[match[1].toUpperCase()]+(match[1]===match[1].toLowerCase()?12:0)+(match[2]==="'"?12:match[2]===','?-12:0);
        const oscillator=audio.createOscillator(), gain=audio.createGain();
        oscillator.type='triangle'; oscillator.frequency.value=440*Math.pow(2,(midi-69)/12);
        gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.16,start+.015);gain.gain.exponentialRampToValueAtTime(.001,start+duration*.9);
        oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(start);oscillator.stop(start+duration);
      }
      start += duration;
    });
  }
  function preview(container,abc) {
    container.replaceChildren();
    const paper=document.createElement('div');container.append(paper);
    if (window.ABCJS) ABCJS.renderAbc(paper,abc,{responsive:'resize',clickListener:(element)=>{
      const anchor=document.querySelector('#comment-anchor'),scope=document.querySelector('#comment-scope');
      if(anchor && element.startChar !== undefined) {anchor.value=`Tune characters ${element.startChar}–${element.endChar}: ${abc.slice(element.startChar,element.endChar)}`;scope.value='tune';}
    }});
    else paper.textContent='Notation renderer unavailable. Melody source is preserved.';
    const playButton=document.createElement('button');playButton.type='button';playButton.textContent='▶ Play melody';playButton.onclick=()=>play(abc);container.append(playButton);
    const stop=document.createElement('button');stop.type='button';stop.textContent='■ Stop';stop.onclick=()=>{if(audio) audio.close();audio=null;};container.append(stop);
  }
  document.querySelectorAll('.music-display').forEach(el=>{if(el.dataset.content) preview(el,el.dataset.content);else el.textContent='No melody yet.';});
  document.querySelectorAll('.part-editor[data-kind="tune"]').forEach(form=>{
    const field=form.querySelector('textarea');
    if(!field.value.trim()) field.value=initial;
    const tools=form.querySelector('.melody-tools');
    const description=document.createElement('p');description.textContent='Melody sketch: C major, 4/4. Choose a duration and add notes. Add a bar line every four beats. Advanced ABC notation can be entered above; this simple audio preview supports natural notes and rests only.';tools.append(description);
    const duration=document.createElement('select');duration.setAttribute('aria-label','Note duration');
    [['/2','Eighth note'],['','Quarter note'],['2','Half note'],['4','Whole note']].forEach(([value,text])=>{const option=new Option(text,value);duration.add(option);});duration.value='';tools.append(duration);
    const buttons=document.createElement('div');buttons.className='note-buttons';tools.append(buttons);
    const history=[];const canvas=document.createElement('div');tools.append(canvas);
    function add(token){history.push(field.value);field.value += token+' ';preview(canvas,field.value);}
    ['C','D','E','F','G','A','B','c','d','e','f','g','z','|'].forEach(note=>{const b=document.createElement('button');b.type='button';b.textContent=note==='z'?'Rest':note==='|'?'Bar line':note===note.toLowerCase()?note.toUpperCase()+' ↑':note;b.onclick=()=>add(note+(note==='|'?'':duration.value));buttons.append(b);});
    const undo=document.createElement('button');undo.type='button';undo.textContent='Undo last addition';undo.onclick=()=>{if(history.length){field.value=history.pop();preview(canvas,field.value);}};buttons.append(undo);
    field.addEventListener('input',()=>preview(canvas,field.value));preview(canvas,field.value);
  });
  document.querySelectorAll('.panel .prose').forEach(el=>el.addEventListener('mouseup',()=>{
    const selection=window.getSelection();const text=selection.toString().trim();
    if(!text || !el.contains(selection.anchorNode)||!el.contains(selection.focusNode))return;
    const anchor=document.querySelector('#comment-anchor');const scope=document.querySelector('#comment-scope');
    if(anchor){anchor.value=text.slice(0,500);const heading=el.closest('.panel').querySelector('h2').textContent.toLowerCase();if(['concept','lyrics'].includes(heading))scope.value=heading;}
  }));
})();
