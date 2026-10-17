(() => {
  const workspace = document.querySelector('#song-workspace');
  if (!workspace) return;
  const connection = document.querySelector('#connection-status');
  const initialRevision = Number(workspace.dataset.revision);
  const initialStage = workspace.dataset.stage;
  let currentRevision = initialRevision;
  let annotations = [];
  let commentVersion = '';
  let polling = false;
  const commentForm = document.querySelector('#comment-form');
  const editors = [...document.querySelectorAll('.part-editor')].map(form => ({
    form, panel: form.closest('.composition-part'), details: form.closest('details'),
    field: form.querySelector('[name=content]'), status: form.querySelector('.editor-status'),
    saved: form.dataset.saveFailed ? (form.closest('.composition-part').querySelector('.annotated-text')?.textContent ?? form.closest('.composition-part').querySelector('.music-display')?.dataset.content ?? '').replace(/\r\n?/g,'\n') : form.querySelector('[name=content]').value, busy:false, conflict:false, timer:null,
    remote: null, ready:false, leaseBusy:false,
  }));
  function dirty(editor) {return editor.field.value !== editor.saved;}
  function token() {return document.querySelector('[name=csrfmiddlewaretoken]')?.value;}
  async function post(data) {
    const response = await fetch(window.location.pathname, {method:'POST', body:data,
      headers:{Accept:'application/json', 'X-CSRFToken':token() || ''}});
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('Connection interrupted. Your text is still here. Check that you are signed in.');
    }
    const result = await response.json();
    if (!response.ok) {const error=new Error(result.error || 'Unable to save yet.');error.status=response.status;throw error;}
    return result;
  }
  function showConflict(editor, remote) {
    editor.conflict = true;
    editor.ready = false;
    editor.form.querySelector('.conflict-panel').hidden = false;
    editor.form.querySelector('.latest-content').value = remote.content;
    editor.status.textContent = 'A newer version was shared. Your text has been kept for comparison.';
  }
  function focusComment(id) {
    const bubble = document.getElementById(`comment-${id}`);
    if (!bubble) return;
    document.querySelectorAll('.is-focused').forEach(el=>el.classList.remove('is-focused'));
    bubble.open = true; bubble.classList.add('is-focused');
    bubble.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  function drawAnnotations(panel, content, revision) {
    const prose = panel.querySelector('.annotated-text');
    if (!prose) return;
    const matches = annotations.filter(a=>a.scope===panel.dataset.kind && a.revision===revision && a.anchor);
    // Keep ranges unambiguous: only exact, uniquely occurring quotations on this revision.
    const ranges = matches.map(a=>({...a, start:content.indexOf(a.anchor)}))
      .filter(a=>a.start>=0 && content.indexOf(a.anchor,a.start+1)===-1).sort((a,b)=>a.start-b.start);
    const fragment=document.createDocumentFragment();let cursor=0;
    ranges.forEach(a=>{
      if(a.start<cursor) return;
      fragment.append(document.createTextNode(content.slice(cursor,a.start)));
      const mark=document.createElement('mark');mark.className='annotation';mark.tabIndex=0;
      mark.textContent=a.anchor;mark.setAttribute('role','button');mark.setAttribute('aria-label',`Read comment on ${a.anchor}`);
      mark.onclick=()=>focusComment(a.id);mark.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focusComment(a.id);}};
      fragment.append(mark);cursor=a.start+a.anchor.length;
    });
    fragment.append(document.createTextNode(content.slice(cursor)));
    // Do not replace nodes underneath an active text selection.
    const selection=window.getSelection();
    if(selection && !selection.isCollapsed && prose.contains(selection.anchorNode)) return;
    prose.replaceChildren(fragment);
  }
  function applyState(state) {
    if(state.revision < currentRevision) return;
    currentRevision = state.revision;
    annotations = state.annotations;
    document.querySelector('#composition-credits').textContent=state.contributors.join(', ');
    document.querySelector('#stage-label').textContent = state.stage_label;
    if (state.revision !== initialRevision || state.stage !== initialStage) {
      document.querySelector('#review-refresh').hidden=false;
      document.querySelectorAll('.review-action button').forEach(b=>b.disabled=true);
    }
    const list = document.querySelector('#comment-list');
    if(commentVersion !== state.comments_html) {
      const closed=new Set([...list.querySelectorAll('details:not([open])')].map(el=>el.id));
      list.innerHTML=state.comments_html; // Escaped server-rendered template, never raw user HTML.
      closed.forEach(id=>{const el=document.getElementById(id);if(el) el.open=false;});
      commentVersion=state.comments_html;
    }
    state.parts.forEach(part=>{
      const panel=document.querySelector(`#part-${part.kind}`);
      const editor=editors.find(e=>e.panel===panel);
      panel.querySelector('.approval-count').textContent=`${part.approvals}/2 experienced approvals`;
      panel.querySelector('.presence').textContent=part.editor && !part.editing_here ? `${part.editor} is editing ${part.kind}…` : '';
      const previousRevision=Number(panel.dataset.revision);
      panel.dataset.revision=part.revision;
      if(part.content) panel.querySelector('.empty-hint')?.remove();
      if(part.license) {
        const credit=panel.querySelector('.part-license');credit.replaceChildren();
        const link=document.createElement('a');link.href='https://creativecommons.org/licenses/by/4.0/';link.rel='license';link.textContent='CC BY 4.0';
        credit.append(link,document.createTextNode(' · credit the contributors'));
      }
      if(part.kind==='tune') {
        const display=panel.querySelector('.music-display');
        if(display.dataset.content!==part.content) {
          display.dataset.content=part.content;
          window.dispatchEvent(new CustomEvent('melody:refresh',{detail:{container:display,content:part.content}}));
        }
      } else drawAnnotations(panel,part.content,part.revision);
      if(editor) {
        editor.remote=part;

        const localRevision=Number(editor.form.elements.revision.value);
        if(!editor.busy && part.revision!==localRevision) {
          if(dirty(editor)) showConflict(editor,part);
          else {
            editor.field.value=part.content;editor.saved=editor.field.value;
            editor.form.elements.revision.value=part.revision;
            if(part.kind==='tune') editor.field.dispatchEvent(new Event('melody:updated'));
          }
        }
        editor.form.elements.song_revision.value=state.revision;
        if(state.stage!==initialStage || !state.can_edit) {
          editor.ready=false;editor.field.readOnly=true;
          editor.status.textContent='Editing permissions or review stage changed. Keep a copy of any unsaved text, then refresh.';
        } else if(part.editor && !part.editing_here && !dirty(editor)) {
          editor.field.readOnly=true;editor.ready=false;
          editor.status.textContent=`${part.editor} is writing. Their changes will appear here.`;
        } else if(!editor.conflict) editor.field.readOnly=false;
      }
      if(previousRevision!==part.revision && commentForm?.elements.scope.value===part.kind && commentForm.elements.anchor.value) {
        document.querySelector('#comment-status').textContent='The selected section changed. Select the phrase again before sharing.';
      }
    });
    if(commentForm && !commentForm.elements.anchor.value) commentForm.elements.song_revision.value=state.revision;
    connection.textContent='Up to date · changes and comments appear automatically.';
    connection.classList.remove('connection-error');
  }
  async function poll() {
    if(polling || document.hidden) return;
    polling=true;
    try {
      const response=await fetch(workspace.dataset.stateUrl,{cache:'no-store'});
      if(!response.ok) throw new Error('Unavailable');
      const state=await response.json();
      // A save in flight must finish before we adopt its returned revision.
      if(!editors.some(e=>e.busy)) applyState(state);
    } catch {
      connection.textContent='Connection interrupted. Unsaved text stays in your editor; reconnecting…';
      connection.classList.add('connection-error');
    } finally {polling=false;}
  }
  async function reserve(editor) {
    if(editor.leaseBusy || editor.busy || editor.conflict || !editor.details.open || editor.form.elements.stage.value!==initialStage) return;
    editor.leaseBusy=true;
    const data=new FormData(editor.form);data.set('action','lock');
    try {
      const state=await post(data);editor.ready=true;
      if(!dirty(editor))editor.status.textContent='Ready to write · changes save automatically.';
      applyState(state);
    } catch(error) {
      editor.ready=false;editor.status.textContent=error.message;
    } finally {editor.leaseBusy=false;}
  }
  async function save(editor) {
    if(editor.busy || editor.conflict || !dirty(editor)) return;
    if(!editor.field.value.trim()) {editor.status.textContent='Add some text to save this section.';return;}
    editor.busy=true;editor.status.textContent='Saving…';
    const content=editor.field.value;
    const data=new FormData(editor.form);data.set('action','autosave');
    try {
      const state=await post(data);
      const part=state.parts.find(p=>p.kind===editor.panel.dataset.kind);
      editor.saved=content;editor.form.elements.revision.value=part.revision;
      editor.form.elements.song_revision.value=state.revision;
      editor.status.textContent=dirty(editor)?'Saving your latest changes…':'All changes saved';
      applyState(state);
    } catch(error) {
      editor.status.textContent=error.message;
      if(error.status===409) {
        editor.conflict=true;
        editor.busy=false;
        await poll();
        if(editor.remote) showConflict(editor,editor.remote);
      }
    } finally {
      editor.busy=false;
      if(dirty(editor) && !editor.conflict) schedule(editor,3000);
    }
  }
  function schedule(editor,delay=1000) {
    clearTimeout(editor.timer);editor.timer=setTimeout(()=>save(editor),delay);
  }
  editors.forEach(editor=>{
    editor.field.addEventListener('input',()=>{
      editor.status.textContent='Unsaved changes…';schedule(editor);
    });
    editor.form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(editor.timer);save(editor);});
    editor.details.addEventListener('toggle',()=>{
      if(editor.details.open) reserve(editor);
      else if(!dirty(editor) && !editor.busy) {
        const data=new FormData(editor.form);data.set('action','release');
        post(data).then(applyState).catch(()=>{});
      }
    });
    editor.form.querySelector('.use-latest').onclick=()=>{
      if(!editor.remote) return;
      editor.field.value=editor.remote.content;editor.saved=editor.field.value;
      editor.form.elements.revision.value=editor.remote.revision;
      editor.conflict=false;editor.form.querySelector('.conflict-panel').hidden=true;
      editor.status.textContent='Latest saved version restored. You can continue editing.';
      if(editor.panel.dataset.kind==='tune')editor.field.dispatchEvent(new Event('melody:updated'));
      reserve(editor);
    };
  });
  document.querySelector('#collapse-comments').onclick=event=>{
    const collapse=event.target.textContent==='Collapse all';
    document.querySelectorAll('#comment-list details').forEach(el=>el.open=!collapse);
    event.target.textContent=collapse?'Expand all':'Collapse all';
  };
  function setCommentRevision() {
    if(!commentForm) return;
    const panel=document.querySelector(`#part-${commentForm.elements.scope.value}`);
    commentForm.elements.part_revision.value=panel?.dataset.revision || '';
    commentForm.elements.song_revision.value=currentRevision;
  }
  window.addEventListener('comment:anchor',setCommentRevision);
  document.querySelectorAll('.annotated-text').forEach(prose=>prose.addEventListener('mouseup',()=>{
    if(!commentForm) return;
    const selection=window.getSelection();const text=selection.toString().trim();
    if(!text || !prose.contains(selection.anchorNode)||!prose.contains(selection.focusNode))return;
    commentForm.elements.anchor.value=text.slice(0,500);
    commentForm.elements.scope.value=prose.dataset.scope;
    setCommentRevision();
    document.querySelector('.comment-composer').open=true;
  }));
  if(commentForm) {
    commentForm.elements.scope.onchange=()=>{commentForm.elements.anchor.value='';setCommentRevision();};
    commentForm.elements.anchor.addEventListener('input',setCommentRevision);
    commentForm.addEventListener('submit',async event=>{
      event.preventDefault();const status=document.querySelector('#comment-status');
      if(!commentForm.elements.anchor.value)setCommentRevision();
      status.textContent='Sharing…';
      try {
        const state=await post(new FormData(commentForm));
        commentForm.elements.body.value='';commentForm.elements.anchor.value='';
        commentForm.elements.part_revision.value='';
        status.textContent='Your thought has been shared.';applyState(state);
      } catch(error) {status.textContent=error.message;}
    });
  }
  window.addEventListener('beforeunload',event=>{
    if(editors.some(e=>dirty(e)||e.busy) || commentForm?.elements.body.value.trim()) {event.preventDefault();event.returnValue='';}
  });
  setInterval(poll,3000);
  setInterval(()=>editors.forEach(reserve),10000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  poll();
})();
