(() => {
  const replace = image => {
    if (!image || image.tagName !== 'IMG' || !image.closest('main')) return;
    const fallback = document.createElement('span');
    fallback.className = `${image.className || ''} image-load-fallback`;
    fallback.setAttribute('role', 'img');
    fallback.setAttribute('aria-label', `${image.alt || 'Bild'} – nicht verfügbar`);
    fallback.textContent = '📚';
    image.replaceWith(fallback);
  };
  document.addEventListener('error', event => replace(event.target), true);
  document.querySelectorAll('main img[src]').forEach(image => {
    if (image.complete && image.naturalWidth === 0) replace(image);
  });
})();
