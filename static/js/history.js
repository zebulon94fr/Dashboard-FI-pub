import { Store, comptes } from './state.js';
import { api } from './api.js';
import { fmtN, esc, destroyChart, makeChart, messageCanvas, fmtChart } from './core.js';
import { chartColors } from './theme.js';
import { couleursComptes, couleurIndex } from './colors.js';

let periode = 90;
let BENCHMARKS = null;          // cache de la réponse /api/benchmark
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
  renderBenchmarkChecks();
  renderHistory();
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
      statut.textContent = `✓ ${noms.join(', ')} — base ${fmtN(BENCHMARKS.capital_depart)} € au ${BENCHMARKS.date_debut}`;
    }
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

  const labels = hist.map(h => h.date);
  const rayon = hist.length <= 5 ? 5 : hist.length <= 30 ? 3 : 0;
  const options = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12, pointStyle: 'line', usePointStyle: true } },
      tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label} : ${fmtChart(ctx.raw)}` } },
    },
    scales: {
      x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, maxTicksLimit: 8 } },
      y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtChart } },
    },
  };

  // ── Indices, alignés sur les dates de l'historique ──────────
  const sets = [];
  Object.keys(BENCHMARKS?.benchmarks || {}).forEach((nom, i) => {
    if (!selection.has(nom)) return;
    const points = BENCHMARKS.benchmarks[nom] || [];
    const parDate = Object.fromEntries(points.map(p => [p.date, p.valeur]));
    const dates = points.map(p => p.date).sort();
    const aligne = hist.map(h => {
      let valeur = null;
      for (const d of dates) {
        if (d <= h.date) valeur = parDate[d]; else break;
      }
      return valeur;
    });
    if (aligne.some(v => v != null)) {
      sets.push({
        label: nom, data: aligne,
        borderColor: couleurBenchmark(i), backgroundColor: 'transparent',
        fill: false, tension: .3, pointRadius: 0, pointHoverRadius: 5,
        borderWidth: 1.5, borderDash: [5, 4],
      });
    }
  });

  makeChart('chartHistTotal', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Portefeuille', data: hist.map(h => h.total),
        borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.08)',
        fill: true, tension: .3, pointRadius: rayon, pointHoverRadius: 6, borderWidth: 2.5,
      }, ...sets],
    },
    options,
  });

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
