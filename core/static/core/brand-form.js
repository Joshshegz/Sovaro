(() => {
  const form = document.querySelector('[data-brand-form]');
  const progress = document.querySelector('[data-brand-progress]');
  if (!form || !progress) return;

  const initialRequiredFields = [...form.querySelectorAll('input[required], textarea[required], select[required]')];
  const bar = progress.querySelector('[data-progress-bar]');
  const label = progress.querySelector('[data-progress-label]');
  const detail = progress.querySelector('[data-progress-detail]');
  const track = progress.querySelector('[role="progressbar"]');

  const hasValue = (field) => field.type === 'checkbox' ? field.checked : Boolean(field.value.trim());
  const updateProgress = () => {
    const requiredFields = [...form.querySelectorAll('input[required], textarea[required], select[required]')];
    const complete = requiredFields.filter(hasValue).length;
    const percent = requiredFields.length ? Math.round((complete / requiredFields.length) * 100) : 100;
    bar.style.width = `${percent}%`;
    label.textContent = percent === 100 ? 'Ready to continue' : `${percent}% complete`;
    detail.textContent = `${complete} of ${requiredFields.length} essential details added`;
    track.setAttribute('aria-valuenow', String(percent));
    progress.classList.toggle('is-complete', percent === 100);
  };

  initialRequiredFields.forEach((field) => {
    field.addEventListener('input', updateProgress);
    field.addEventListener('change', updateProgress);
  });
  updateProgress();

  const toneField = form.querySelector('#id_tone_of_voice');
  const customToneField = form.querySelector('#id_custom_tone');
  const customToneWrapper = customToneField?.closest('.field-custom_tone');
  if (toneField && customToneField && customToneWrapper) {
    const updateToneChoice = () => {
      const isCustom = toneField.value === 'other';
      customToneWrapper.hidden = !isCustom;
      customToneField.required = isCustom;
      customToneField.setAttribute('aria-required', String(isCustom));
      customToneWrapper.classList.toggle('is-revealed', isCustom);
    };
    toneField.addEventListener('change', () => {
      updateToneChoice();
      if (toneField.value === 'other') customToneField.focus();
      updateProgress();
    });
    customToneField.addEventListener('input', updateProgress);
    updateToneChoice();
  }

  const suggestButton = form.querySelector('[data-audience-suggest]');
  const suggestionStatus = form.querySelector('[data-audience-status]');
  const audienceField = form.querySelector('#id_target_audience');
  if (suggestButton && suggestionStatus && audienceField) {
    suggestButton.addEventListener('click', async () => {
      const nicheField = form.querySelector('#id_niche');
      const modelField = form.querySelector('#id_business_model');
      if (!nicheField.value.trim() || !modelField.value.trim()) {
        suggestionStatus.textContent = 'Add the industry and business model first.';
        suggestionStatus.className = 'audience-suggestion-status is-error';
        (!nicheField.value.trim() ? nicheField : modelField).focus();
        return;
      }

      const originalText = suggestButton.innerHTML;
      suggestButton.disabled = true;
      suggestButton.setAttribute('aria-busy', 'true');
      suggestButton.innerHTML = '<span class="button-spinner" aria-hidden="true"></span> Building suggestion…';
      suggestionStatus.textContent = 'Looking at the brand details you entered.';
      suggestionStatus.className = 'audience-suggestion-status is-working';

      try {
        const response = await fetch(form.dataset.audienceUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value },
          body: JSON.stringify({
            brand_name: form.querySelector('#id_name')?.value || '',
            niche: nicheField.value,
            business_model: modelField.value,
            primary_goal: form.querySelector('#id_primary_goal')?.value || '',
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'We could not build a suggestion right now.');
        audienceField.value = data.suggestion;
        audienceField.dispatchEvent(new Event('input', { bubbles: true }));
        suggestionStatus.textContent = data.source === 'starter'
          ? 'Starter draft added. AI was unavailable, so review and personalise it.'
          : data.source === 'groq'
            ? 'Backup AI completed this draft because Gemini was unavailable. Review and personalise it.'
            : 'AI draft added. Edit it with what you know about real customers.';
        suggestionStatus.className = 'audience-suggestion-status is-success';
        suggestButton.innerHTML = '<span aria-hidden="true">↻</span> Regenerate suggestion';
      } catch (error) {
        suggestionStatus.textContent = error.message;
        suggestionStatus.className = 'audience-suggestion-status is-error';
        suggestButton.innerHTML = originalText;
      } finally {
        suggestButton.disabled = false;
        suggestButton.removeAttribute('aria-busy');
      }
    });
  }
})();
