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

  const competitorButton = form.querySelector('[data-competitor-suggest]');
  const competitorStatus = form.querySelector('[data-competitor-status]');
  const competitorList = form.querySelector('[data-competitor-list]');
  const competitorField = form.querySelector('#id_competitor_notes');
  if (competitorButton && competitorStatus && competitorList && competitorField) {
    competitorButton.addEventListener('click', async () => {
      const industryField = form.querySelector('#id_niche');
      if (!industryField?.value.trim()) {
        competitorStatus.textContent = 'Add the industry first.';
        competitorStatus.className = 'competitor-suggestion-status is-error';
        industryField?.focus();
        return;
      }
      const originalText = competitorButton.innerHTML;
      competitorButton.disabled = true;
      competitorButton.setAttribute('aria-busy', 'true');
      competitorButton.innerHTML = '<span class="button-spinner" aria-hidden="true"></span> Searching...';
      competitorStatus.textContent = 'Checking current public social activity. This may take a moment.';
      competitorStatus.className = 'competitor-suggestion-status is-working';
      competitorList.replaceChildren();
      try {
        const response = await fetch(form.dataset.competitorUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value },
          body: JSON.stringify({
            brand_name: form.querySelector('#id_name')?.value || '',
            industry: industryField.value,
            audience: form.querySelector('#id_target_audience')?.value || '',
            location: '',
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Competitor search could not be completed.');
        const competitors = data.competitors || [];
        if (!competitors.length) {
          competitorStatus.textContent = 'No competitors met the two-platform activity rule. Add known competitors manually if needed.';
          competitorStatus.className = 'competitor-suggestion-status is-empty';
          return;
        }
        competitors.forEach((competitor) => {
          const card = document.createElement('article');
          const platforms = (competitor.platforms || []).map((item) => item.platform).join(' + ');
          const links = (competitor.platforms || []).map((item) => item.url).join(' | ');
          const line = `${competitor.name} | ${platforms} | ${links}`;
          card.innerHTML = `<div><strong>${escapeHtml(competitor.name)}</strong><span>${escapeHtml(competitor.relationship || 'Competitor')}</span></div><p>${escapeHtml(competitor.why_relevant || '')}</p><small>${escapeHtml(platforms)} - recent public activity found</small><button type="button" class="button secondary">Add competitor</button>`;
          card.querySelector('button').addEventListener('click', () => {
            const existing = competitorField.value.trim();
            if (!existing.includes(competitor.name)) competitorField.value = existing ? `${existing}\n${line}` : line;
            competitorField.dispatchEvent(new Event('input', { bubbles: true }));
            card.classList.add('is-added');
            card.querySelector('button').textContent = 'Added';
            card.querySelector('button').disabled = true;
          });
          competitorList.appendChild(card);
        });
        competitorStatus.textContent = `${competitors.length} active competitor${competitors.length === 1 ? '' : 's'} found. Choose the relevant ones.`;
        competitorStatus.className = 'competitor-suggestion-status is-success';
      } catch (error) {
        competitorStatus.textContent = error.message;
        competitorStatus.className = 'competitor-suggestion-status is-error';
      } finally {
        competitorButton.disabled = false;
        competitorButton.removeAttribute('aria-busy');
        competitorButton.innerHTML = originalText;
      }
    });
  }

  function escapeHtml(value) {
    const node = document.createElement('div');
    node.textContent = value || '';
    return node.innerHTML;
  }
})();
