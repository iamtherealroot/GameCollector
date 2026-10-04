(() => {
  const form = document.getElementById('copy-form');
  if (!form) return;
  const field = name => form.querySelector(`[name="${name}"]`);
  const box = field('box_present');
  const media = field('media_present');
  const manual = field('manual_present');
  const sealed = field('sealed');
  const format = field('ownership_format');
  const sync = () => {
    const digital = format && format.value === 'digital';
    if (sealed && sealed.checked && !digital) {
      for (const part of [box, media, manual]) if (part) part.checked = true;
    }
    for (const [part, name] of [[box, 'box_condition'], [media, 'media_condition']]) {
      const input = field(name);
      if (input) input.disabled = digital || !part || !part.checked;
    }
  };
  for (const part of [box, media, manual]) {
    if (part) part.addEventListener('change', () => {
      if (!part.checked && sealed) sealed.checked = false;
      sync();
    });
  }
  if (sealed) sealed.addEventListener('change', sync);
  if (format) format.addEventListener('change', sync);
  sync();
})();
