// Centralise tous les appels réseau vers /api/*.
const BASE = window.location.origin;

async function json(url, options) {
  const r = await fetch(url, options);
  let body = null;
  try { body = await r.json(); } catch { /* réponse vide ou non JSON */ }
  if (!r.ok) throw new Error(body?.error || `Erreur ${r.status}`);
  return body;
}

const post = (url, payload) => json(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});

const put = (url, payload) => json(url, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});

export const api = {
  // ── Référentiel & portefeuille ──
  getAccountTypes:  ()   => json(`${BASE}/api/account-types`),
  getData:          ()   => json(`${BASE}/api/data`),
  getStats:         ()   => json(`${BASE}/api/stats`),
  getQuotes:        ()   => json(`${BASE}/api/quotes`),

  // ── Comptes ──
  getAccounts:      ()          => json(`${BASE}/api/accounts`),
  createAccount:    (payload)   => post(`${BASE}/api/accounts`, payload),
  updateAccount:    (id, p)     => put(`${BASE}/api/accounts/${id}`, p),
  deleteAccount:    (id)        => json(`${BASE}/api/accounts/${id}`, { method: 'DELETE' }),
  saveCibles:       (cibles)    => post(`${BASE}/api/accounts/cibles`, { cibles }),

  // ── Positions ──
  createPosition:   (accountId, p) => post(`${BASE}/api/accounts/${accountId}/positions`, p),
  updatePosition:   (id, p)        => put(`${BASE}/api/positions/${id}`, p),
  deletePosition:   (id)           => json(`${BASE}/api/positions/${id}`, { method: 'DELETE' }),

  // ── Dividendes ──
  getDividendes({ annee, account_id } = {}) {
    const params = new URLSearchParams();
    if (annee) params.set('annee', annee);
    if (account_id) params.set('account_id', account_id);
    const q = params.toString();
    return json(`${BASE}/api/dividendes${q ? '?' + q : ''}`);
  },
  createDividende:  (p)     => post(`${BASE}/api/dividendes`, p),
  updateDividende:  (id, p) => put(`${BASE}/api/dividendes/${id}`, p),
  deleteDividende:  (id)    => json(`${BASE}/api/dividendes/${id}`, { method: 'DELETE' }),
  getTri: (nom, accountId) =>
    json(`${BASE}/api/tri?nom=${encodeURIComponent(nom)}&account_id=${accountId}`),

  // ── Divers ──
  getBenchmark:     (days) => json(`${BASE}/api/benchmark?days=${days}`),
  getSettingsKey:   ()     => json(`${BASE}/api/settings/key`),
  saveSettings:     (key)  => post(`${BASE}/api/settings`, { anthropicKey: key }),
  claude:           (p)    => post(`${BASE}/api/claude`, p),
  sendTelegramSummary: ()  => json(`${BASE}/api/telegram/send`, { method: 'POST' }),
  exportCsvUrl:     ()     => `${BASE}/api/export/csv`,
};
