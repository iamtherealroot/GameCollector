(() => {
  document.querySelectorAll('[data-category-icon-picker]').forEach(picker => {
    if (picker.dataset.initialized) return;
    picker.dataset.initialized = 'true';
    const select = picker.querySelector('[data-category-icon-select]');
    const field = picker.querySelector('[data-category-custom-field]');
    const input = picker.querySelector('[data-category-custom-input]');
    const update = () => {
      const custom = select.value === '__custom__';
      field.hidden = !custom;
      input.disabled = !custom;
    };
    select.addEventListener('change', update);
    update();
  });
})();
