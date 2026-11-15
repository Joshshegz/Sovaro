(() => {
  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    const wrapper = button.closest('.password-input');
    const input = wrapper?.querySelector('input');
    const label = input?.closest('.auth-field')?.querySelector('label')?.textContent?.trim() || 'password';
    if (!input) return;

    button.addEventListener('click', () => {
      const isVisible = input.type === 'text';
      input.type = isVisible ? 'password' : 'text';
      button.setAttribute('aria-pressed', String(!isVisible));
      button.setAttribute('aria-label', `${isVisible ? 'Show' : 'Hide'} ${label.toLowerCase()}`);
      button.querySelector('.toggle-text').textContent = isVisible ? 'Show' : 'Hide';
    });
  });
})();
