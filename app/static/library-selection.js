(() => {
  const checks = [...document.querySelectorAll('.library-select-copy')];
  const page = document.getElementById('library-select-page');
  const button = document.getElementById('library-edit-selected');
  const count = document.getElementById('library-selection-count');
  if (!page || !button || !count) return;
  const update = () => {
    const selected = checks.filter(input => input.checked).length;
    count.textContent = `${selected} ausgewählt`;
    button.disabled = selected === 0;
    page.disabled = checks.length === 0;
    page.checked = checks.length > 0 && selected === checks.length;
    page.indeterminate = selected > 0 && selected < checks.length;
  };
  page.addEventListener('change', () => { checks.forEach(input => { input.checked = page.checked; }); update(); });
  checks.forEach(input => input.addEventListener('change', update));
  update();
})();
