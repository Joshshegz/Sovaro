(() => {
  const storageKey = 'sovaro-theme';
  const root = document.documentElement;
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');

  const storedTheme = () => {
    try { return localStorage.getItem(storageKey); } catch (_) { return null; }
  };

  const applyTheme = (theme, persist = false) => {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    if (themeMeta) themeMeta.content = theme === 'dark' ? '#0d1324' : '#f6f8fc';
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const isDark = theme === 'dark';
      button.setAttribute('aria-pressed', String(isDark));
      button.setAttribute('aria-label', `Switch to ${isDark ? 'light' : 'dark'} mode`);
      button.title = `Switch to ${isDark ? 'light' : 'dark'} mode`;
    });
    if (persist) {
      try { localStorage.setItem(storageKey, theme); } catch (_) {}
    }
  };

  applyTheme(root.dataset.theme || (systemTheme.matches ? 'dark' : 'light'));
  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark', true));
  });
  systemTheme.addEventListener('change', (event) => {
    if (!storedTheme()) applyTheme(event.matches ? 'dark' : 'light');
  });
})();
