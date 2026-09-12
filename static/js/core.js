import { Store, typeInfo } from './state.js';
import { api } from './api.js';
import { renderOverview } from './overview.js';
import { renderSidebar, renderComptesPage, renderAccountPage } from './accounts.js';
import { renderHistory } from './history.js';
import { simUpdate } from './simulation.js';
import { loadDividendes } from './dividendes.js';
import { loadTransactions } from './transactions.js';
import { renderFiscalite } from './fiscalite.js';
import { renderRebalancing } from './rebalancing.js';

// ══════════════════════════════════════════════════════════════
// NAVIGATION
// ══════════════════════════════════════════════════════════════
export function showTab(tab) {
  const estCompte = tab.startsWith('compte-');
  const sectionId = estCompte ? 'compte' : tab;

  document.querySelectorAll('[data-tab]').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  const toggle = document.getElementById('comptesToggle');
  if (estCompte || tab === 'comptes') {
    toggle.classList.add('active');
    openComptesMenu();
  } else {
    toggle.classList.remove('active');
  }

  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById('sec-' + sectionId).classList.add('active');

  if (estCompte) { Store.currentAccountId = Number(tab.slice('compte-'.length)); renderAccountPage(); }
  if (tab === 'comptes')     renderComptesPage();
  if (tab === 'history')     renderHistory();
  if (tab === 'simulation')  simUpdate();
  if (tab === 'dividendes')  loadDividendes();
  if (tab === 'transactions') loadTransactions();
  if (tab === 'fiscalite')   renderFiscalite();
  if (tab === 'rebalancing') renderRebalancing();

  closeSidebar();
}

export const showAccount = id => showTab('compte-' + id);

function openComptesMenu() {
  document.getElementById('comptesSubmenu').classList.add('open');
  document.getElementById('comptesToggle').classList.add('open');
}

export function toggleComptesMenu() {
  document.getElementById('comptesSubmenu').classList.toggle('open');
  document.getElementById('comptesToggle').classList.toggle('open');
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

export function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('open');
}

// ══════════════════════════════════════════════════════════════
// RENDU
// ══════════════════════════════════════════════════════════════
export function render() {
  renderSidebar();
  renderOverview();
  renderComptesPage();
  if (Store.currentAccountId) renderAccountPage();
}

/**
 * Agrégats calculés côté serveur (variation 24 h, journées extrêmes, cours
 * périmés). Jamais bloquant : l'interface reste complète s'ils manquent.
 */
export async function fetchStats() {
  try {
    return await api.getStats();
  } catch {
    return null;
  }
}

/** Recharge le portefeuille depuis le serveur puis rafraîchit l'affichage. */
export async function reload() {
  Store.DATA = await api.getData();
  Store.STATS = await fetchStats();
  render();
}

// ══════════════════════════════════════════════════════════════
// FORMATAGE
// ══════════════════════════════════════════════════════════════
const HIDDEN = '<span class="amount-hidden">██████</span>';

export const fmt = v => {
  if (v == null) return '—';
  if (Store.amountsHidden) return HIDDEN;
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v) + ' €';
};

export const fmtN = v => v == null ? '—'
  : new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);

/** Montant affiché dans un graphique (axe ou infobulle) : suit le bouton « masquer ». */
export const fmtChart = v => {
  if (v == null) return '—';
  if (Store.amountsHidden) return '•••';
  return v >= 1e6 ? `${+(v / 1e6).toFixed(2)} M €` : `${fmtN(v)} €`;
};

export const fmtP = v => v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';

export const cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : 'neu';

export const sum = arr => arr.reduce((a, b) => a + b, 0);

/** Quantité, avec la précision propre au type d'enveloppe (8 décimales en crypto). */
export const fmtQty = (v, decimales = 4) => v == null ? '—'
  : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: decimales }).format(v);

/** Montant dans sa devise d'origine (le cours d'une action américaine reste en $). */
export const fmtDevise = (v, devise = 'EUR') => {
  if (v == null) return '—';
  const decimales = Math.abs(v) < 1 ? 4 : 2;
  const n = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(v);
  return `${n} ${devise === 'EUR' ? '€' : devise}`;
};

export const fmtDate = iso => {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString('fr-FR');
};

/** Échappe le texte saisi par l'utilisateur avant injection dans du HTML. */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function kpiCard(label, value, sub = '', subCls = '') {
  return `<div class="card">
    <div class="card-label">${esc(label)}</div>
    <div class="card-value">${value}</div>
    ${sub ? `<div class="card-sub ${subCls}">${sub}</div>` : ''}
  </div>`;
}

export function badgeType(type) {
  const t = typeInfo(type);
  return `<span class="tag" style="background:${t.couleur}26;color:${t.couleur}">${esc(t.label)}</span>`;
}

export function emptyState(titre, texte, bouton = '') {
  return `<div class="empty-state">
    <div class="empty-state-icon">📭</div>
    <div class="empty-state-title">${esc(titre)}</div>
    <div class="empty-state-text">${esc(texte)}</div>
    ${bouton}
  </div>`;
}

export function toggleHide() {
  Store.amountsHidden = !Store.amountsHidden;
  const btn = document.getElementById('btnHide');
  btn.textContent = Store.amountsHidden ? '🙈' : '👁';
  btn.classList.toggle('active', Store.amountsHidden);
  render();
}

export function destroyChart(id) {
  if (Store.charts[id]) { Store.charts[id].destroy(); delete Store.charts[id]; }
}

/** Écrit un message centré directement sur un canvas (graphique vide ou indisponible). */
export function messageCanvas(canvas, texte) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim();
  ctx.font = '13px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(texte, canvas.width / 2, Math.min(80, canvas.height / 2));
}

/**
 * Crée un graphique en remplaçant le précédent. Si Chart.js n'a pas pu être
 * chargé, le reste de l'application continue de fonctionner : seul le canvas
 * affiche un message, aucune exception ne remonte.
 */
export function makeChart(id, config) {
  destroyChart(id);
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  if (typeof Chart === 'undefined') {
    messageCanvas(canvas, 'Graphiques indisponibles (Chart.js non chargé)');
    return null;
  }
  Store.charts[id] = new Chart(canvas, config);
  return Store.charts[id];
}

/** Nombre saisi dans un formulaire : accepte « 1 234,56 » comme « 1234.56 ». */
export const parseNum = s => parseFloat(String(s ?? '').replace(/\s/g, '').replace(',', '.')) || 0;
