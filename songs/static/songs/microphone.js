// Native browser capture, converted locally to mono WAV for the existing uploader.
(() => {
  const OfflineContext=window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const supported=window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder && OfflineContext && window.DataTransfer;
  const MAX_SECONDS=300, SAMPLE_RATE=24000, MAX_BYTES=25*1024*1024;
  let active=null;
  const controllers=[];
  function time(seconds) {
    const whole=Math.floor(seconds);return `${Math.floor(whole/60)}:${String(whole%60).padStart(2,'0')}`;
  }
  async function toWav(blob) {
    const context=new OfflineContext(1,1,SAMPLE_RATE);
    const decoded=await context.decodeAudioData(await blob.arrayBuffer());
    const bytes=44+decoded.length*2;
    if(!decoded.length || bytes>MAX_BYTES)throw new Error('This take is too long. Record a shorter take, up to five minutes.');
    const buffer=new ArrayBuffer(bytes), view=new DataView(buffer);
    function text(offset,value){for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));}
    text(0,'RIFF');view.setUint32(4,bytes-8,true);text(8,'WAVE');text(12,'fmt ');
    view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
    view.setUint32(24,decoded.sampleRate,true);view.setUint32(28,decoded.sampleRate*2,true);
    view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,bytes-44,true);
    const channels=Array.from({length:decoded.numberOfChannels},(_,i)=>decoded.getChannelData(i));
    for(let i=0;i<decoded.length;i++) {
      let sample=0;for(const channel of channels)sample+=channel[i];
      sample=Math.max(-1,Math.min(1,sample/channels.length));
      view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true);
    }
    return new File([buffer],`microphone-${new Date().toISOString().replace(/[:.]/g,'-')}.wav`,{type:'audio/wav'});
  }
  document.querySelectorAll('.microphone-recorder').forEach(widget=>{
    const form=widget.closest('form'), input=form.elements.recording;
    const label=widget.dataset.recorderLabel;
    const record=widget.querySelector('[data-record]'), stop=widget.querySelector('[data-stop]');
    const cancel=widget.querySelector('[data-cancel]'), discard=widget.querySelector('[data-discard]');
    const timer=widget.querySelector('.recording-timer'), status=widget.querySelector('.microphone-status');
    const preview=widget.querySelector('.microphone-preview'), audio=preview.querySelector('audio');
    const submissions=[...form.querySelectorAll('button[name=action],button[type=submit]')];
    let state='idle', stream=null, recorder=null, chunks=[], interval=null, started=0;
    let generation=0, previewUrl=null, uploading=false, capturedRevision=null;
    const controller={cancel:()=>{if(state!=='idle')cancelTake();}};controllers.push(controller);
    function stopTracks(){if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}}
    function sync() {
      if(state==='idle')delete form.dataset.micActive;else form.dataset.micActive=state;
      record.disabled=!supported || state!=='idle' || uploading;
      record.textContent=input.files.length?'● Record again':'● Record';
      record.setAttribute('aria-label',`Record ${label}${input.files.length?' again':''}`);
      stop.hidden=state!=='recording';stop.disabled=state!=='recording';
      cancel.hidden=state==='idle';cancel.disabled=state==='idle';
      timer.hidden=state!=='recording';
      input.disabled=state!=='idle' || uploading;
      discard.disabled=state!=='idle' || uploading;
      submissions.forEach(button=>button.disabled=state!=='idle' || uploading);
      preview.hidden=!previewUrl || state!=='idle';
    }
    function clearPreview() {
      audio.pause();audio.removeAttribute('src');audio.load();
      if(previewUrl)URL.revokeObjectURL(previewUrl);
      previewUrl=null;preview.hidden=true;
    }
    function showSelected() {
      clearPreview();
      if(input.files[0]){previewUrl=URL.createObjectURL(input.files[0]);audio.src=previewUrl;}
      sync();
    }
    function finish(message) {
      clearInterval(interval);interval=null;stopTracks();
      state='idle';if(active===controller)active=null;
      if(message)status.textContent=message;
      sync();
    }
    function cancelTake() {
      generation++;
      if(recorder && recorder.state!=='inactive')recorder.stop();
      chunks=[];
      finish(input.files.length?'Recording cancelled. Your previous selection is kept.':'Recording cancelled.');
    }
    function stopTake() {
      if(state!=='recording' || !recorder)return;
      state='processing';status.textContent='Preparing your take…';clearInterval(interval);interval=null;
      recorder.stop();stopTracks();sync();
    }
    record.onclick=async()=>{
      if(!supported || uploading || state!=='idle')return;
      if(active && active!==controller){status.textContent='Finish the other recording first.';return;}
      active=controller;state='requesting';const attempt=++generation;
      capturedRevision=form.elements.revision?.value;
      status.textContent='Allow microphone access in your browser to begin. Nothing is shared yet.';sync();
      try {
        const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:{ideal:1},echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
        if(attempt!==generation){acquired.getTracks().forEach(track=>track.stop());return;}
        stream=acquired;
        document.querySelectorAll('audio').forEach(player=>player.pause());
        window.dispatchEvent(new Event('playback:recording'));
        const type=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
        const capture=new MediaRecorder(stream,type?{mimeType:type,audioBitsPerSecond:96000}:{audioBitsPerSecond:96000});
        recorder=capture;chunks=[];let encodedBytes=0;
        capture.ondataavailable=event=>{
          if(attempt!==generation || !event.data.size)return;
          chunks.push(event.data);encodedBytes+=event.data.size;
          if(encodedBytes>=MAX_BYTES && state==='recording')stopTake();
        };
        capture.onerror=()=>{if(attempt!==generation)return;generation++;finish('Recording stopped unexpectedly. Please try again, or choose a file.');};
        capture.onstop=async()=>{
          if(attempt!==generation)return;
          state='processing';clearInterval(interval);interval=null;stopTracks();
          status.textContent='Preparing your take…';sync();
          const blob=new Blob(chunks,{type:capture.mimeType || chunks[0]?.type});chunks=[];
          try {
            const file=await toWav(blob);
            if(attempt!==generation)return;
            const selection=new DataTransfer();selection.items.add(file);input.files=selection.files;
            state='idle';input.dispatchEvent(new Event('change',{bubbles:true}));
            if(capturedRevision!==undefined)form.elements.revision.value=capturedRevision;
            finish('Take ready. Listen below, then upload or share when you are happy with it.');
          } catch(error) {
            if(attempt===generation)finish(error.message.includes('shorter take')?error.message:'Could not prepare this take. Try recording again, or choose an audio file.');
          }
        };
        capture.start(1000);state='recording';started=performance.now();timer.value='0:00';
        status.textContent='Recording… microphone is on. Maximum five minutes.';sync();
        interval=setInterval(()=>{
          const seconds=(performance.now()-started)/1000;timer.value=time(seconds);
          if(seconds>=MAX_SECONDS)stopTake();
        },200);
        stream.getTracks().forEach(track=>track.addEventListener('ended',()=>{if(attempt===generation && state==='recording')stopTake();}));
      } catch(error) {
        if(attempt!==generation)return;
        const message=error.name==='NotAllowedError'?'Microphone access was not allowed. Allow it in your browser’s site settings, or choose a file.':
          error.name==='NotFoundError'?'No microphone was found. Connect one, or choose a file.':
          error.name==='NotReadableError'?'The microphone is unavailable or in use. Close other recording apps and try again.':
          'Could not start the microphone. Try again, or choose a file.';
        finish(message);
      }
    };
    stop.onclick=stopTake;cancel.onclick=cancelTake;
    discard.onclick=()=>{input.value='';input.dispatchEvent(new Event('change',{bubbles:true}));status.textContent='Take discarded. Record again or choose a file.';};
    input.addEventListener('change',()=>{
      showSelected();
      if(state==='idle')status.textContent=input.files.length?'Ready to preview. Nothing is shared until you upload or share.':'Record here, or choose a file above.';
    });
    form.addEventListener('audio:upload-start',()=>{uploading=true;sync();});
    form.addEventListener('audio:upload-finished',()=>{uploading=false;sync();});
    form.addEventListener('audio:uploaded',()=>{clearPreview();status.textContent='Recording shared.';sync();});
    if(!supported)status.textContent=window.isSecureContext?'Microphone recording is not supported in this browser. You can still choose an audio file.':'Microphone recording needs HTTPS or localhost. You can still choose an audio file.';
    sync();
  });
  window.addEventListener('pagehide',()=>controllers.forEach(controller=>controller.cancel()));
})();
