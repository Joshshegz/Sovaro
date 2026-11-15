(() => {
  const documentView = document.querySelector('[data-client-strategy]');
  if (!documentView) return;
  const notesButton = document.querySelector('[data-strategy-notes]');
  const internalNotes = documentView.querySelector('[data-internal-notes]');
  const status = document.querySelector('[data-strategy-status]');

  notesButton?.addEventListener('click', () => {
    const hidden = internalNotes.toggleAttribute('hidden');
    notesButton.textContent = hidden ? 'Show internal notes' : 'Hide internal notes';
    notesButton.setAttribute('aria-pressed', String(!hidden));
    status.textContent = hidden ? 'Client view is ready. Internal notes are hidden.' : 'Internal review notes are visible.';
  });

  document.querySelector('[data-strategy-copy]')?.addEventListener('click', async () => {
    const copy = documentView.cloneNode(true);
    copy.querySelectorAll('[data-no-copy], [hidden]').forEach((item) => item.remove());
    try {
      await navigator.clipboard.writeText(copy.innerText.trim());
      status.textContent = 'Strategy copied. You can paste it into a document or email.';
    } catch (_) {
      status.textContent = 'Copy was blocked by the browser. Select the strategy text and copy it manually.';
    }
  });

  document.querySelector('[data-strategy-print]')?.addEventListener('click', () => window.print());
})();
