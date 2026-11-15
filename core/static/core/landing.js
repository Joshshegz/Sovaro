(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const header = document.querySelector('.landing-header');

  const updateHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 16);
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });

  if (reduceMotion) return;

  document.documentElement.classList.add('landing-motion');
  const revealItems = document.querySelectorAll(
    '.trust-strip, .section-copy, .section-heading-centred, .problem-grid article, .workflow-grid article, .audience-copy, .audience-panel, .landing-cta'
  );
  revealItems.forEach((item, index) => {
    item.classList.add('reveal-item');
    item.style.setProperty('--reveal-delay', `${Math.min(index % 3, 2) * 90}ms`);
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.14, rootMargin: '0px 0px -7% 0px' });
  revealItems.forEach((item) => observer.observe(item));

  const stage = document.querySelector('.product-stage');
  const product = document.querySelector('.product-window');
  if (stage && product && window.matchMedia('(pointer: fine)').matches) {
    stage.addEventListener('pointermove', (event) => {
      const rect = stage.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      product.style.setProperty('--pointer-x', `${x * 2.2}deg`);
      product.style.setProperty('--pointer-y', `${y * -1.8}deg`);
    });
    stage.addEventListener('pointerleave', () => {
      product.style.setProperty('--pointer-x', '0deg');
      product.style.setProperty('--pointer-y', '0deg');
    });
  }
})();
