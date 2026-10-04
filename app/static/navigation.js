(() => {
  document.querySelectorAll('[data-nav-search]').forEach(input => {
    const scope = input.closest('.bibo-menu-panel, .bibo-mobile-panel, .panel');
    const sections = scope.querySelectorAll('[data-nav-section], [data-nav-group]');
    const empty = scope.querySelector('[data-nav-empty]');
    const normalize = text => text.toLocaleLowerCase('de').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    input.addEventListener('input', () => {
      const words = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
      let total = 0;
      sections.forEach(section => {
        let count = 0;
        section.querySelectorAll('[data-nav-link]').forEach(link => {
          const visible = words.every(word => normalize(link.textContent).includes(word));
          link.hidden = !visible;
          if (visible) count++;
        });
        section.hidden = count === 0;
        if (section.tagName === 'DETAILS') section.open = words.length > 0 && count > 0;
        total += count;
      });
      empty.hidden = total > 0;
    });
  });
  document.querySelectorAll('.bibo-nav [data-nav-group]').forEach(menu => {
    menu.addEventListener('toggle', () => {
      if (menu.open && !menu.closest('.bibo-menu-panel')?.querySelector('[data-nav-search]')?.value.trim()) document.querySelectorAll('.bibo-nav [data-nav-group]').forEach(other => { if (other !== menu) other.open = false; });
    });
  });
  const menus = () => document.querySelectorAll('.bibo-nav details[open], .bibo-mobile-menu[open], .account-menu[open]');
  document.addEventListener('click', event => menus().forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const open = [...menus()];
      const active = open.find(menu => menu.contains(document.activeElement));
      open.forEach(menu => { menu.open = false; });
      if (active) active.querySelector('summary').focus();
    }
  });
  document.querySelectorAll('.bibo-mobile-menu a').forEach(link => link.addEventListener('click', () => { link.closest('.bibo-mobile-menu').open = false; }));
})();
