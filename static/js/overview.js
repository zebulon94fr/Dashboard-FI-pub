import { Store, typeInfo, comptes, toutesPositions, totalPortefeuille, investiPortefeuille } from './state.js';
import { chartColors } from './theme.js';
import { fmt, fmtP, cls, kpiCard, destroyChart, makeChart, fmtChart } from './core.js';
import { couleursComptes, couleurIndex, alpha } from './colors.js';
import { renderAlertes, renderCalendrier, renderFaits, clearAlertes } from './alertes.js';

const ID_CHARTS = ['chartAlloc', 'chartType', 'chartPerf', 'chartTop10', 'chartSecteur', 'chartGeo'];

export function renderOverview() {
  const liste = comptes();
  const vide = document.getElementById('overviewEmpty');
  const corps = document.getElementById('overviewBody');

  if (!liste.length) {
    ID_CHARTS.forEach(destroyChart);
    clearAlertes();
    corps.style.display = 'none';
    vide.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">📊</div>
      <div class="empty-state-title">Bienvenue sur votre tableau de bord</div>
      <div class="empty-state-text">
        Commencez par créer un compte : PEA, compte-titres, PER, assurance vie,
        métaux précieux ou cryptomonnaies. Vous pourrez ensuite y ajouter vos positions
        et suivre leur valorisation en direct.
      </div>
      <button class="btn primary" onclick="openAccountModal()">+ Créer mon premier compte</button>
    </div>`;
    return;
  }

  vide.innerHTML = '';
  corps.style.display = '';

  const total = totalPortefeuille();
  const investi = investiPortefeuille();
  const pvLatent = liste.reduce((s, c) => s + (c.pv_latent || 0), 0);
  const pvGlobal = investi ? pvLatent / investi : 0;
  const couleurs = couleursComptes(liste);

  // ── KPIs ────────────────────────────────────────────────────
  const var24h = Store.STATS?.var24h;

  document.getElementById('overviewCards').innerHTML =
    kpiCard('Patrimoine total', fmt(total), fmtP(pvGlobal), cls(pvGlobal)) +
    (var24h != null
      ? kpiCard('Variation 24 h', fmt(var24h), fmtP(Store.STATS.var24h_pct), cls(var24h))
      : '') +
    kpiCard('Investi', fmt(investi), `${liste.length} compte${liste.length > 1 ? 's' : ''}`, 'neu') +
    kpiCard('+/- Latent', fmt(pvLatent), fmtP(pvGlobal), cls(pvLatent)) +
    liste.map(c => kpiCard(c.nom, fmt(c.valorisation), fmtP(c.pv_pct), cls(c.pv_pct))).join('');

  // ── Alertes, calendrier fiscal et faits marquants ───────────
  renderAlertes();
  renderCalendrier();
  renderFaits();

  ID_CHARTS.forEach(destroyChart);

  const optionsDoughnut = {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12, font: { size: 11 } } },
      tooltip: {
        callbacks: {
          label: ctx => {
            const somme = ctx.dataset.data.reduce((a, b) => a + b, 0);
            return ` ${fmtChart(ctx.raw)} (${somme ? (ctx.raw / somme * 100).toFixed(1) : 0} %)`;
          },
        },
      },
    },
  };

  // ── Répartition par compte ──────────────────────────────────
  const actifs = liste.map((c, i) => ({ ...c, couleur: couleurs[i] })).filter(c => c.valorisation > 0);
  makeChart('chartAlloc', {
    type: 'doughnut',
    data: {
      labels: actifs.map(c => c.nom),
      datasets: [{ data: actifs.map(c => c.valorisation), backgroundColor: actifs.map(c => c.couleur), borderWidth: 0, hoverOffset: 6 }],
    },
    options: optionsDoughnut,
  });

  // ── Répartition par type d'enveloppe ────────────────────────
  const parType = {};
  for (const c of liste) {
    const t = typeInfo(c.type);
    const agrege = parType[c.type] ||= { label: t.label, couleur: t.couleur, valorisation: 0 };
    agrege.valorisation += c.valorisation || 0;
  }
  const types = Object.values(parType).filter(t => t.valorisation > 0);
  makeChart('chartType', {
    type: 'doughnut',
    data: {
      labels: types.map(t => t.label),
      datasets: [{ data: types.map(t => t.valorisation), backgroundColor: types.map(t => t.couleur), borderWidth: 0, hoverOffset: 6 }],
    },
    options: optionsDoughnut,
  });

  // ── Performance par compte ──────────────────────────────────
  makeChart('chartPerf', {
    type: 'bar',
    data: {
      labels: liste.map(c => c.nom),
      datasets: [{
        data: liste.map(c => +((c.pv_pct || 0) * 100).toFixed(2)),
        backgroundColor: liste.map(c => (c.pv_pct || 0) >= 0 ? 'rgba(63,185,80,.7)' : 'rgba(248,81,73,.7)'),
        borderRadius: 5,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted } },
        y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: v => v + '%' } },
      },
    },
  });

  // ── Top 10 positions ────────────────────────────────────────
  const top = toutesPositions()
    .filter(p => (p.valorisation || 0) > 0)
    .sort((a, b) => (b.valorisation || 0) - (a.valorisation || 0))
    .slice(0, 10);

  makeChart('chartTop10', {
    type: 'bar',
    data: {
      labels: top.map(p => p.nom.length > 20 ? p.nom.slice(0, 20) + '…' : p.nom),
      datasets: [{
        data: top.map(p => p.valorisation),
        backgroundColor: top.map(p => alpha(typeInfo(p._compte.type).couleur, 0.75)),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${fmtChart(ctx.raw)} — ${top[ctx.dataIndex]._compte.nom}` } },
      },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtChart } },
        y: { grid: { display: false }, ticks: { color: chartColors().muted, font: { size: 11 } } },
      },
    },
  });

  // ── Secteurs & zones géographiques (champs libres des positions) ──
  repartitionLibre('chartSecteur', 'hintSecteur', 'secteur',
    'Renseignez le champ « Secteur » d\'une position pour alimenter ce graphique.', optionsDoughnut);
  repartitionLibre('chartGeo', 'hintGeo', 'zone',
    'Renseignez le champ « Zone géographique » d\'une position pour alimenter ce graphique.', optionsDoughnut);
}

function repartitionLibre(canvasId, hintId, champ, aide, options) {
  const positions = toutesPositions().filter(p => (p.valorisation || 0) > 0);
  const agrege = {};
  let renseignees = 0;

  for (const p of positions) {
    const cle = (p[champ] || '').trim() || 'Non renseigné';
    if (cle !== 'Non renseigné') renseignees++;
    agrege[cle] = (agrege[cle] || 0) + p.valorisation;
  }

  const entrees = Object.entries(agrege).sort((a, b) => b[1] - a[1]);
  const hint = document.getElementById(hintId);
  hint.textContent = renseignees ? '' : aide;

  makeChart(canvasId, {
    type: 'doughnut',
    data: {
      labels: entrees.map(e => e[0]),
      datasets: [{
        data: entrees.map(e => e[1]),
        backgroundColor: entrees.map(([nom], i) => nom === 'Non renseigné' ? '#484f58' : couleurIndex(i)),
        borderWidth: 0, hoverOffset: 6,
      }],
    },
    options,
  });
}
