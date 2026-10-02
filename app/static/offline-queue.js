(() => {
  'use strict';

  const DB_NAME = 'gamecollector-offline-v219';
  const STORE = 'captures';
  const DB_VERSION = 1;
  let syncing = false;

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, {keyPath: 'id'});
          store.createIndex('created_at', 'created_at');
          store.createIndex('barcode', 'barcode');
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function transaction(mode, action) {
    return openDb().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const store = tx.objectStore(STORE);
      let result;
      try { result = action(store); } catch (error) { reject(error); return; }
      tx.oncomplete = () => { db.close(); resolve(result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
      tx.onabort = () => { db.close(); reject(tx.error); };
    }));
  }

  function uuid() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'capture-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  function cleanBarcode(value) {
    return String(value || '').replace(/\D/g, '');
  }

  async function list() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const request = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();
      request.onsuccess = () => { db.close(); resolve((request.result || []).filter(row => String(row.user_id || '') === String(window.GC_CURRENT_USER_ID || '')).sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))); };
      request.onerror = () => { db.close(); reject(request.error); };
    });
  }

  async function count() {
    const rows = await list();
    return rows.length;
  }

  async function addBarcode(value, source='scanner') {
    const barcode = cleanBarcode(value);
    if (![8, 12, 13].includes(barcode.length)) throw new Error('Ungültige EAN/UPC');
    const existing = (await list()).find(row => row.barcode === barcode);
    if (existing) return {capture: existing, duplicate: true};
    if (!window.GC_CURRENT_USER_ID) throw new Error('Bitte zuerst wieder anmelden');
    const capture = {id: uuid(), user_id: window.GC_CURRENT_USER_ID, barcode, source, created_at: new Date().toISOString()};
    await transaction('readwrite', store => store.put(capture));
    await updateStatus();
    document.dispatchEvent(new CustomEvent('gc:offline-queue-changed', {detail: {count: await count()}}));
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then(registration => {
        if (registration.sync) registration.sync.register('gc-sync-captures').catch(() => {});
      }).catch(() => {});
    }
    return {capture, duplicate: false};
  }

  async function remove(ids) {
    if (!ids.length) return;
    await transaction('readwrite', store => ids.forEach(id => store.delete(id)));
  }

  async function sync() {
    if (syncing || !navigator.onLine) return {ok: false, offline: true};
    const captures = await list();
    if (!captures.length) { await updateStatus(); return {ok: true, empty: true}; }
    syncing = true;
    await updateStatus('syncing');
    try {
      const response = await fetch('/api/offline/captures/sync', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({captures}),
      });
      const contentType = response.headers.get('content-type') || '';
      if (!response.ok || !contentType.includes('application/json')) throw new Error('Synchronisierung nicht möglich');
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || 'Synchronisierung fehlgeschlagen');
      const accepted = (payload.results || []).filter(row => row.accepted).map(row => row.id);
      await remove(accepted);
      document.dispatchEvent(new CustomEvent('gc:offline-synced', {detail: payload}));
      return payload;
    } catch (error) {
      return {ok: false, error: error.message || String(error)};
    } finally {
      syncing = false;
      await updateStatus();
    }
  }

  async function updateStatus(forced='') {
    const banner = document.getElementById('offline-sync-status');
    const label = document.getElementById('offline-sync-label');
    const badge = document.getElementById('offline-sync-count');
    if (!banner || !label || !badge) return;
    let pending = 0;
    try { pending = await count(); } catch (_) {}
    badge.textContent = String(pending);
    badge.hidden = pending === 0;
    banner.classList.toggle('is-offline', !navigator.onLine);
    banner.classList.toggle('has-pending', pending > 0);
    banner.classList.toggle('needs-https', !window.isSecureContext);
    if (!window.isSecureContext) label.textContent = 'Für Installation, Kamera und zuverlässigen Offline-Betrieb Bibo über HTTPS öffnen';
    else if (forced === 'syncing') label.textContent = 'Offline-Erfassungen werden synchronisiert …';
    else if (!navigator.onLine) label.textContent = pending ? `Offline · ${pending} Erfassung(en) lokal gespeichert` : 'Offline · Scans werden lokal gespeichert';
    else if (pending) label.textContent = `${pending} lokale Erfassung(en) warten auf Synchronisierung`;
    else label.textContent = 'Online · Offline-Erfassung bereit';
    // The normal online/empty state needs no permanent banner. Keep the
    // status visible only when the user must notice or act on something.
    banner.hidden = window.isSecureContext && navigator.onLine && pending === 0 && forced !== 'syncing';
  }

  window.GameCollectorOfflineQueue = {addBarcode, list, count, sync, updateStatus};
  window.addEventListener('online', () => { updateStatus(); sync(); });
  window.addEventListener('offline', () => updateStatus());
  document.addEventListener('DOMContentLoaded', () => { updateStatus(); if (navigator.onLine) sync(); });
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', event => {
      if (event.data && event.data.type === 'gc-sync-captures') sync();
    });
  }
})();
