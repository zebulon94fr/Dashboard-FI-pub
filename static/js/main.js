// Point d'entrée : charge le référentiel puis le portefeuille, et expose sur
// `window` les fonctions référencées par les attributs onclick="" du HTML.
import { Store, comptes } from './state.js';
import { api } from './api.js';
import { initTheme, toggleTheme } from './theme.js';
import { showTab, showAccount, render, reload, toggleHide, toggleComptesMenu, toggleSidebar } from './core.js';
import {
  openAccountModal, closeAccountModal, saveAccount, selectAccountType,
  editCurrentAccount, deleteCurrentAccount, delPos,
} from './accounts.js';
import {
  openPositionModal, closeModal, savePosition,
  onPositionAccountChange, onPositionDeviseChange,
} from './positions.js';
import {
  openDivModal, closeDivModal, saveDividende, deleteDividende,
  editDividende, loadDividendes, onDividendeAccountChange,
} from './dividendes.js';
import { setPeriod, loadBenchmark, renderHistory, toggleBenchmark } from './history.js';
import { setSimReturn, simUpdate } from './simulation.js';
import { showFiscTab, renderFiscalite, calcFisc } from './fiscalite.js';
import { rbSliderChange, rbSauvegarderCibles, rbCalculer } from './rebalancing.js';
import { saveKey, analyzeIA } from './ia.js';

// ══════════════════════════════════════════════════════════════
// COURS
// ══════════════════════════════════════════════════════════════
async function refreshQuotes() {
  const positions = comptes().reduce((s, c) => s + c.nb_positions, 0);
  if (!positions) { setQuoteStatus('', 'Aucune position à actualiser'); return; }

  setQuoteStatus('loading', 'Récupération des cours…');
  document.getElementById('btnRefresh').disabled = true;
  try {
    const r = await api.getQuotes();
    await reload();
    const heure = r.lastUpdate
      ? new Date(r.lastUpdate).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
      : '—';
    setQuoteStatus(r.ok ? 'ok' : '', r.ok
      ? `${r.positions} position${r.positions > 1 ? 's' : ''} à jour à ${heure}`
      : 'Aucun cours récupéré — vérifiez les tickers');
  } catch (e) {
    setQuoteStatus('error', 'Erreur : ' + e.message);
  }
  document.getElementById('btnRefresh').disabled = false;
}

function setQuoteStatus(etat, libelle) {
  document.getElementById('quoteDot').className =
    'dot ' + (etat === 'loading' ? 'loading' : etat === 'ok' ? 'ok' : '');
  document.getElementById('quoteLabel').textContent = libelle;
}

function exportCSV() { window.open(api.exportCsvUrl(), '_blank'); }

// ══════════════════════════════════════════════════════════════
// TELEGRAM
// ══════════════════════════════════════════════════════════════
async function sendTelegramSummary() {
  const btn = document.getElementById('btnTelegram');
  const libelle = btn.textContent;
  btn.disabled = true;
  btn.textContent = '⏳ Envoi…';
  try {
    await api.sendTelegramSummary();
    btn.textContent = '✓ Envoyé';
  } catch (e) {
    btn.textContent = '✗ Erreur';
    console.error('Telegram :', e.message);
  }
  setTimeout(() => { btn.textContent = libelle; btn.disabled = false; }, 2500);
}

// ══════════════════════════════════════════════════════════════
// INITIALISATION
// ══════════════════════════════════════════════════════════════
async function init() {
  initTheme();

  // Référentiel des types d'enveloppes (source unique : catalog.py).
  try {
    const referentiel = await api.getAccountTypes();
    Store.TYPES_LIST = referentiel.types || [];
    Store.TYPES = Object.fromEntries(Store.TYPES_LIST.map(t => [t.id, t]));
    Store.DEVISES = referentiel.devises || ['EUR'];
  } catch (e) {
    setQuoteStatus('error', 'Serveur injoignable');
    console.error('Référentiel :', e.message);
  }

  // Clé API : serveur en priorité, localStorage en repli.
  try {
    const { key } = await api.getSettingsKey();
    if (key) {
      document.getElementById('apiKey').value = key;
      localStorage.setItem('dashboardfi_apiKey', key);
    } else {
      document.getElementById('apiKey').value = localStorage.getItem('dashboardfi_apiKey') || '';
    }
  } catch {
    document.getElementById('apiKey').value = localStorage.getItem('dashboardfi_apiKey') || '';
  }

  try {
    Store.DATA = await api.getData();
  } catch (e) {
    setQuoteStatus('error', 'Serveur injoignable');
  }

  render();
  refreshQuotes();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}

// ══════════════════════════════════════════════════════════════
// Handlers utilisés par les onclick="" du HTML statique
// ══════════════════════════════════════════════════════════════
Object.assign(window, {
  showTab, showAccount, toggleTheme, toggleHide, toggleComptesMenu, toggleSidebar,
  refreshQuotes, exportCSV, sendTelegramSummary,
  openAccountModal, closeAccountModal, saveAccount, selectAccountType,
  editCurrentAccount, deleteCurrentAccount, delPos,
  openPositionModal, closeModal, savePosition, onPositionAccountChange, onPositionDeviseChange,
  openDivModal, closeDivModal, saveDividende, deleteDividende, editDividende,
  loadDividendes, onDividendeAccountChange,
  setPeriod, loadBenchmark, renderHistory, toggleBenchmark,
  setSimReturn, simUpdate,
  showFiscTab, renderFiscalite, calcFisc,
  rbSliderChange, rbSauvegarderCibles, rbCalculer,
  saveKey, analyzeIA,
});

init();
