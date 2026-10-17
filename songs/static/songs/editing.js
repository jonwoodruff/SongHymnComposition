// Reserve a section without navigating away from unsaved work.
document.querySelectorAll('.section-editor').forEach(editor => {
  const form = editor.querySelector('.lock-form');
  const status = editor.querySelector('.lock-status');
  let pending = false;
  async function acquire() {
    if (pending) return;
    pending = true;
    status.textContent = 'Reserving this section…';
    const data = new FormData(form);
    data.set('action', 'lock');
    try {
      const response = await fetch(form.action || window.location.href, {
        method: 'POST', body: data, headers: {Accept: 'application/json'}
      });
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Could not reserve this section. Keep a copy of your text and check that you are still signed in.');
      }
      const result = await response.json();
      status.textContent = result.error || result.message;
    } catch (error) {
      status.textContent = error.message || 'Unable to reserve this section. Your text is still in the editor.';
    } finally { pending = false; }
  }
  editor.addEventListener('toggle', () => { if (editor.open) acquire(); });
  form.addEventListener('submit', event => {event.preventDefault(); acquire();});
});
