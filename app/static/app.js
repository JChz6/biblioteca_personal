(() => {
  const header = document.getElementById('site-header');
  const menu = document.getElementById('menu-toggle');
  const account = document.querySelector('.account-menu');
  let lastY = window.scrollY;
  let scheduled = false;
  const showHeader = () => header.classList.remove('is-hidden');
  function closeMenu() {
    header.classList.remove('menu-open');
    menu.setAttribute('aria-expanded', 'false');
    menu.setAttribute('aria-label', menu.dataset.labelOpen);
  }
  menu.addEventListener('click', () => {
    const open = !header.classList.contains('menu-open');
    header.classList.toggle('menu-open', open);
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? menu.dataset.labelClose : menu.dataset.labelOpen);
    showHeader();
  });
  header.addEventListener('focusin', showHeader);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (header.classList.contains('menu-open')) { closeMenu(); menu.focus(); }
      account.open = false;
    }
  });
  document.addEventListener('click', event => {
    if (!header.contains(event.target)) closeMenu();
    if (!account.contains(event.target)) account.open = false;
  });
  window.addEventListener('scroll', () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      const y = Math.max(0, window.scrollY);
      const delta = y - lastY;
      if (y < 80 || header.classList.contains('menu-open') || account.open || header.querySelector(':focus-visible')) showHeader();
      else if (Math.abs(delta) > 6) header.classList.toggle('is-hidden', delta > 0);
      if (Math.abs(delta) > 6 || y < 80) lastY = y;
      scheduled = false;
    });
  }, { passive: true });
  const filterToggle = document.getElementById('filter-toggle');
  filterToggle?.addEventListener('click', () => {
    const expanded = filterToggle.getAttribute('aria-expanded') !== 'true';
    filterToggle.setAttribute('aria-expanded', String(expanded));
    document.getElementById('filter-fields').classList.toggle('is-open', expanded);
  });
  document.querySelectorAll('.catalog-filters select').forEach(select => {
    select.addEventListener('change', () => select.form.requestSubmit());
  });
  const dialog = document.getElementById('godzilla-dialog');
  const trigger = document.getElementById('godzilla-open');
  let savedY = 0;
  trigger?.addEventListener('click', () => {
    savedY = window.scrollY;
    document.body.style.top = `-${savedY}px`;
    document.body.classList.add('modal-open');
    dialog.showModal();
  });
  dialog?.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  dialog?.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog?.addEventListener('close', () => {
    document.body.classList.remove('modal-open');
    document.body.style.top = '';
    window.scrollTo(0, savedY);
    trigger.focus({ preventScroll: true });
  });
})();
