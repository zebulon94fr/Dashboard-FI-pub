import { Store, comptes } from './state.js';
import { api } from './api.js';
import { fmtN, esc, destroyChart, makeChart, messageCanvas, fmtChart } from './core.js';
import { chartColors } from './theme.js';
import { couleursComptes, couleurIndex } from './colors.js';

let periode = 90;
let BENCHMARKS = null;          // cache de la réponse /api/benchmark
let PERF = null;                // cache de la réponse /api/performance (TWR)
let mode = 'euros';             // 'euros' = valorisation, 'base100' = TWR comparable
const selection = new Set();    // indices cochés

export function setPeriod(jours) {
  periode = jours;
  document.querySelectorAll('.period-btn').forEach(b => {
    const label = b.textContent.trim();
    const valeur = label === 'Tout' ? 9999
      : parseInt(label) * (label.includes('A') ? 365 : 1);
    b.classList.toggle('active', valeur === jours);
  });
  BENCHMARKS = null;
  PERF = null;
  renderBenchmarkChecks();
  renderHistory();
}

/**
 * Bascule entre la valorisation en euros et le TWR en base 100.
 *
 * En euros, un versement fait bondir la courbe sans qu'aucun actif n'ait
 * progressé : c'est lisible, mais incomparable à un indice. La base 100
 * neutralise les apports et rend la comparaison honnête.
 */
export async function setBenchmarkMode(nouveauMode) {
  mode = nouveauMode;
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  if (mode === 'base100' && !PERF && !BENCHMARKS) await chargerPerformance();
  renderHistory();
}

async function chargerPerformance() {
  try {
    PERF = (await api.getPerformance(periode === 9999 ? 1825 : periode)).twr;
  } catch {
    PERF = null;
  }
}

/** Série base 100 du portefeuille, d'où qu'elle vienne. */
function serieBase100() {
  return BENCHMARKS?.portfolio_base100 || PERF?.base100 || [];
}

export async function loadBenchmark() {
  const btn = document.getElementById('bmLoadBtn');
  const statut = document.getElementById('bmStatus');
  btn.disabled = true;
  statut.textContent = '⏳ Chargement des indices…';

  try {
    BENCHMARKS = await api.getBenchmark(periode === 9999 ? 1825 : periode);
    const noms = Object.keys(BENCHMARKS.benchmarks || {});
    if (BENCHMARKS.error && !noms.length) {
      statut.textContent = '⚠️ ' + BENCHMARKS.error;
    } else if (!noms.length) {
      statut.textContent = '⚠️ Aucun indice récupéré.';
    } else {
      if (!selection.size) selection.add(noms[0]);
      const twr = BENCHMARKS.twr;
      statut.textContent =
        `✓ ${noms.join(', ')} — converti${noms.length > 1 ? 's' : ''} en euros, depuis le ${BENCHMARKS.date_debut}`
        + (twr != null ? ` · TWR du portefeuille ${(twr >= 0 ? '+' : '') + (twr * 100).toFixed(2)} %` : '')
        + (BENCHMARKS.flux_total ? ` (${fmtN(BENCHMARKS.flux_total)} € de mouvements neutralisés)` : '');
    }
    renderBenchmarkNote();
    renderBenchmarkChecks();
    renderHistory();
  } catch (e) {
    statut.textContent = '⚠️ ' + e.message;
  }
  btn.disabled = false;
}

function couleurBenchmark(i) { return couleurIndex(i + 3); }

function renderBenchmarkChecks() {
  const conteneur = document.getElementById('bmChecks');
  const noms = Object.keys(BENCHMARKS?.benchmarks || {});
  if (!noms.length) {
    conteneur.innerHTML = '<span class="muted" style="font-size:12px">— chargez les indices pour comparer</span>';
    return;
  }
  conteneur.innerHTML = noms.map((nom, i) => `
    <label class="bm-check">
      <input type="checkbox" ${selection.has(nom) ? 'checked' : ''}
             style="accent-color:${couleurBenchmark(i)}"
             onchange="toggleBenchmark('${esc(nom).replace(/'/g, "\\'")}', this.checked)">
      ${esc(nom)}
    </label>`).join('');
}

export function toggleBenchmark(nom, actif) {
  if (actif) selection.add(nom); else selection.delete(nom);
  renderHistory();
}

/** Signale les indices « prix », dont les dividendes sont exclus. */
function renderBenchmarkNote() {
  const zone = document.getElementById('bmNote');
  if (!zone) return;

  const meta = BENCHMARKS?.meta || {};
  const prix = Object.keys(meta).filter(n => meta[n].rendement === 'prix' && !meta[n].ignore);
  const ignores = Object.keys(meta).filter(n => meta[n].ignore);

  const messages = [];
  if (prix.length) {
    messages.push(`${prix.join(', ')} ${prix.length > 1 ? 'sont des indices' : 'est un indice'} `
      + 'de cours : leurs dividendes sont exclus, ce qui les désavantage d\'environ 2 à 3 points par an '
      + 'face à un portefeuille qui les encaisse.');
  }
  if (ignores.length) {
    messages.push(`${ignores.join(', ')} non affiché${ignores.length > 1 ? 's' : ''} — `
      + ignores.map(n => meta[n].ignore).join(', ') + '.');
  }
  zone.textContent = messages.join(' ');
}

export function renderHistory() {
  const brut = Store.DATA.history || [];
  const debut = periode === 9999 ? '0000'
    : new Date(Date.now() - periode * 86400000).toISOString().slice(0, 10);
  const hist = brut.filter(h => h.date >= debut);

  if (!hist.length) {
    ['chartHistTotal', 'chartHistCompt'].forEach(id => {
      destroyChart(id);
      messageCanvas(document.getElementById(id), 'Aucun historique — actualisez les cours pour commencer');
    });
    return;
  }

  const base100 = mode === 'base100';
  const labels = hist.map(h => h.date);
  const rayon = hist.length <= 5 ? 5 : hist.length <= 30 ? 3 : 0;
  const fmtValeur = base100 ? v => (v == null ? '—' : v.toFixed(2)) : fmtChart;

  const options = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12, pointStyle: 'line', usePointStyle: true } },
      tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label} : ${fmtValeur(ctx.raw)}` } },
    },
    scales: {
      x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, maxTicksLimit: 8 } },
      y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtValeur } },
    },
  };

  /** Reporte une série datée sur les dates de l'historique (dernière valeur connue). */
  const aligner = (points, champ) => {
    const parDate = Object.fromEntries(points.map(p => [p.date, p[champ]]));
    const dates = points.map(p => p.date).sort();
    return hist.map(h => {
      let valeur = null;
      for (const d of dates) {
        if (d <= h.date) valeur = parDate[d]; else break;
      }
      return valeur;
    });
  };

  // ── Indices, alignés sur les dates de l'historique ──────────
  const sets = [];
  Object.keys(BENCHMARKS?.benchmarks || {}).forEach((nom, i) => {
    if (!selection.has(nom)) return;
    const aligne = aligner(BENCHMARKS.benchmarks[nom] || [], base100 ? 'base100' : 'valeur');
    if (aligne.some(v => v != null)) {
      sets.push({
        label: nom, data: aligne,
        borderColor: couleurBenchmark(i), backgroundColor: 'transparent',
        fill: false, tension: .3, pointRadius: 0, pointHoverRadius: 5,
        borderWidth: 1.5, borderDash: [5, 4],
      });
    }
  });

  const serie = serieBase100();
  const donneesPortefeuille = base100
    ? (serie.length ? aligner(serie, 'valeur') : [])
    : hist.map(h => h.total);

  makeChart('chartHistTotal', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: base100 ? 'Portefeuille (TWR, base 100)' : 'Portefeuille',
        data: donneesPortefeuille,
        borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.08)',
        fill: true, tension: .3, pointRadius: rayon, pointHoverRadius: 6, borderWidth: 2.5,
      }, ...sets],
    },
    options,
  });

  const aide = document.getElementById('bmModeHint');
  if (aide) {
    aide.textContent = base100
      ? (donneesPortefeuille.length
          ? 'Base 100 : les versements et retraits sont neutralisés. C\'est la seule vue comparable à un indice.'
          : 'Base 100 indisponible — chargez les indices ou enregistrez des mouvements pour calculer le TWR.')
      : 'En euros : la courbe inclut vos versements. Un apport la fait monter sans qu\'aucun actif n\'ait progressé.';
  }

  // ── Une courbe par compte ───────────────────────────────────
  const liste = comptes();
  const couleurs = couleursComptes(liste);
  makeChart('chartHistCompt', {
    type: 'line',
    data: {
      labels,
      datasets: liste.map((c, i) => ({
        label: c.nom,
        data: hist.map(h => h.comptes?.[String(c.id)] ?? 0),
        borderColor: couleurs[i], backgroundColor: 'transparent',
        tension: .3, pointRadius: rayon, pointHoverRadius: 6, borderWidth: 2, fill: false,
      })),
    },
    options,
  });
}
