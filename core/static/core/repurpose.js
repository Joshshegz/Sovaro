(() => {
  const form = document.querySelector('[data-repurpose-form]');
  if (form) {
    const source = form.querySelector('#id_source_content');
    const label = form.querySelector('[data-source-mode-label]');
    const help = form.querySelector('[data-source-help]');
    const updateMode = () => {
      const mode = form.querySelector('input[name="mode"]:checked')?.value || 'repurpose';
      const fresh = mode === 'fresh';
      label.textContent = fresh ? 'ONE OR TWO ROUGH THOUGHTS' : 'ARTICLE, TRANSCRIPT, POST OR NOTES';
      source.placeholder = fresh
        ? 'For example: Small brands do not need to post every day. Consistency should match their real capacity.'
        : 'Paste an article, transcript, newsletter, post, customer interview or detailed notes.';
      help.textContent = fresh
        ? 'Sovaro will develop caption directions without inventing facts or brand experience.'
        : 'Sovaro will preserve your meaning and flag anything it cannot support from this source.';
    };
    form.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener('change', updateMode));
    updateMode();
  }

  const copyText = async (text, button) => {
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(text.trim());
      button.textContent = 'Copied';
    } catch (_) {
      button.textContent = 'Select and copy manually';
    }
    setTimeout(() => { button.textContent = original; }, 1800);
  };

  document.querySelectorAll('[data-copy-output]').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('.output-card').cloneNode(true);
      card.querySelectorAll('button').forEach((item) => item.remove());
      copyText(card.innerText, button);
    });
  });

  const packageButton = document.querySelector('[data-copy-package]');
  packageButton?.addEventListener('click', () => {
    const outputs = document.querySelector('[data-repurpose-outputs]');
    const copy = outputs.cloneNode(true);
    copy.querySelectorAll('button').forEach((item) => item.remove());
    copyText(copy.innerText, packageButton);
  });
})();
