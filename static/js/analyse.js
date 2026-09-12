// Onglet Analyse : risque, concentration, exposition aux devises et
// contribution à la performance. Toutes ces mesures viennent de /api/analyse,
// calculé sur des rendements corrigés des flux.
import { Store } from './state.js';
import { api } from './api.js';
import { fmt, fmtP, cls, esc, kpiCard, badgeType, destroyChart, makeChart, fmtChart } from './core.js';
import { chartColors } from './theme.js';

let periode = 365;
let DONNEES = null;

const el = id => document.getElementById(id);
const pct = (v, d = 1) => v == null ? '—' : (v * 100).toFixed(d).replace('.', ',') + ' %';
const pts = v => v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2).replace('.', ',') + ' pts';

const TH = 'style="padding:7px 10px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
const TD = 'style="padding:7px 10px;border-bottom:1px solid var(--border)"';

export function setAnalysePeriod(jours) {
  periode = jours;
  document.querySelectorAll('#analysePeriodes .period-btn').forEach(b => {
    b.classList.toggle('active', Number(b.dataset.jours) === jours);
  });
  loadAnalyse();
}

export async function loadAnalyse() {
  const zone = el('analyseBody');
  if (!zone) return;

  try {
    DONNEES = await api.getAnalyse(periode);
  } catch (e) {
    el('analyseCards').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  renderRisque(DONNEES.risque);
  renderConcentration(DONNEES.concentration);
  renderDevises(DONNEES.devises);
  renderContributions(DONNEES.contributions);
  renderClasses(DONNEES.classes);
}

// ══════════════════════════════════════════════════════════════
// RISQUE
// ══════════════════════════════════════════════════════════════
function renderRisque(r) {
  const dd = r.drawdown || {};
  const note = el('analyseNote');

  el('analyseCards').innerHTML =
    kpiCard('Volatilité annualisée', pct(r.volatilite),
      r.nb_observations ? `${r.nb_observations} séances observées` : '', 'neu') +
    kpiCard('Perte maximale', pct(dd.drawdown),
      dd.date_creux ? `creux le ${dd.date_creux}` : '', dd.drawdown ? 'neg' : 'neu') +
    kpiCard('Performance annualisée', pct(r.perf_annualisee), 'hors versements', cls(r.perf_annualisee)) +
    kpiCard('Ratio de Sharpe', r.sharpe == null ? '—' : r.sharpe.toFixed(2).replace('.', ','),
      `taux sans risque ${pct(r.taux_sans_risque)}`, cls(r.sharpe));

  note.textContent = r.message || '';
  note.style.display = r.message ? '' : 'none';

  // Détail de la perte maximale : un tableau plutôt qu'un graphique — ce sont
  // quatre valeurs datées, pas une série.
  el('analyseDrawdown').innerHTML = dd.date_creux ? `
    <div class="fisc-line"><span>Sommet précédent</span><span>${esc(dd.date_sommet || '—')}</span></div>
    <div class="fisc-line"><span>Creux</span><span class="neg">${esc(dd.date_creux)} (${pct(dd.drawdown)})</span></div>
    <div class="fisc-line"><span>Durée de la baisse</span><span>${dd.jours_baisse} jours</span></div>
    <div class="fisc-line"><span>Récupération</span><span class="${dd.recupere ? 'pos' : 'neg'}">${
      dd.recupere ? `oui, le ${esc(dd.date_reprise)} (${dd.jours_recuperation} jours)` : 'pas encore atteinte'
    }</span></div>`
    : '<div class="table-empty">Historique insuffisant pour mesurer une baisse.</div>';
}

// ══════════════════════════════════════════════════════════════
// CONCENTRATION
// ══════════════════════════════════════════════════════════════
function renderConcentration(c) {
  if (!c || !c.total) {
    el('analyseConcentration').innerHTML = '<div class="table-empty">Aucune position valorisée.</div>';
    destroyChart('chartConcentration');
    return;
  }

  el('analyseConcKpis').innerHTML =
    kpiCard('Première ligne', pct(c.poids_top1), 'du portefeuille', c.poids_top1 > 0.25 ? 'neg' : 'neu') +
    kpiCard('Top 5', pct(c.poids_top5), `sur ${c.nb_expositions} expositions`, c.poids_top5 > 0.7 ? 'neg' : 'neu') +
    kpiCard('Lignes équivalentes',
      c.lignes_equivalentes == null ? '—' : c.lignes_equivalentes.toFixed(1).replace('.', ','),
      `indice Herfindahl ${c.hhi?.toFixed(3).replace('.', ',') ?? '—'}`, 'neu') +
    kpiCard('Doublons regroupés', `${c.regroupees}`, 'même sous-jacent', 'neu');

  const expositions = c.expositions.slice(0, 10);
  makeChart('chartConcentration', {
    type: 'bar',
    data: {
      labels: expositions.map(e => e.nom.length > 24 ? e.nom.slice(0, 24) + '…' : e.nom),
      datasets: [{
        label: 'Poids dans le portefeuille',
        data: expositions.map(e => +(e.poids * 100).toFixed(2)),
        backgroundColor: expositions.map(e => e.transparise ? '#58a6ff' : '#58a6ff99'),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.raw} % — ${fmtChart(expositions[ctx.dataIndex].valorisation)}`,
            afterLabel: ctx => {
              const e = expositions[ctx.dataIndex];
              return e.nb_lignes > 1 ? `Regroupe : ${e.lignes.join(', ')}` : '';
            },
          },
        },
      },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: v => v + ' %' } },
        y: { grid: { display: false }, ticks: { color: chartColors().muted, font: { size: 11 } } },
      },
    },
  });

  // Le graphique ne porte pas les montants : le tableau les donne, et sert de
  // repli lisible quand les couleurs ne suffisent pas.
  el('analyseConcentration').innerHTML = `
    <thead><tr>
      <th ${TH}>Exposition</th><th ${TH}>Lignes</th>
      <th ${TH} style="text-align:right">Valorisation</th>
      <th ${TH} style="text-align:right">Poids</th>
    </tr></thead><tbody>` +
    c.expositions.map(e => `<tr>
      <td ${TD}>${esc(e.nom)}${e.transparise ? ' <span class="tag tag-mini">transparisé</span>' : ''}</td>
      <td ${TD} class="muted" style="font-size:11.5px">${esc(e.lignes.join(', '))}</td>
      <td ${TD} style="text-align:right">${fmt(e.valorisation)}</td>
      <td ${TD} style="text-align:right;font-weight:600">${pct(e.poids)}</td>
    </tr>`).join('') + '</tbody>';
}

// ══════════════════════════════════════════════════════════════
// DEVISES ET ATTRIBUTION
// ══════════════════════════════════════════════════════════════
function renderDevises(d) {
  if (!d || !d.total) {
    el('analyseDevises').innerHTML = '<div class="table-empty">Aucune position valorisée.</div>';
    destroyChart('chartDevises');
    return;
  }

  // Teintes stables par devise : l'euro garde l'accent, les autres suivent
  // l'ordre fixe du référentiel — jamais l'ordre d'affichage.
  const TEINTES = { EUR: '#58a6ff', USD: '#3fb950', GBP: '#bc8cff', CHF: '#f0883e', JPY: '#f5c518' };
  const couleur = dev => TEINTES[dev] || '#6e7681';

  makeChart('chartDevises', {
    type: 'doughnut',
    data: {
      labels: d.devises.map(x => x.devise),
      datasets: [{
        data: d.devises.map(x => x.valorisation),
        backgroundColor: d.devises.map(x => couleur(x.devise)),
        borderWidth: 2, borderColor: 'transparent', hoverOffset: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${fmtChart(ctx.raw)} (${(ctx.raw / d.total * 100).toFixed(1)} %)`,
          },
        },
      },
    },
  });

  const a = d.attribution || {};
  const total = a.total || 0;
  const part = v => total ? Math.abs(v / total) : 0;

  el('analyseAttribution').innerHTML = `
    <div class="attr-row">
      <span class="attr-label">Effet marché</span>
      <span class="attr-bar"><span style="width:${(part(a.effet_marche) * 100).toFixed(1)}%;background:var(--accent)"></span></span>
      <span class="attr-val ${cls(a.effet_marche)}">${fmt(a.effet_marche)}</span>
    </div>
    <div class="attr-row">
      <span class="attr-label">Effet change</span>
      <span class="attr-bar"><span style="width:${(part(a.effet_change) * 100).toFixed(1)}%;background:var(--orange)"></span></span>
      <span class="attr-val ${cls(a.effet_change)}">${fmt(a.effet_change)}</span>
    </div>
    <div class="attr-row attr-total">
      <span class="attr-label">Plus-value latente</span>
      <span class="attr-bar"></span>
      <span class="attr-val ${cls(total)}">${fmt(total)}</span>
    </div>
    <div class="chart-hint">
      ${d.part_hors_euro > 0
        ? `${pct(d.part_hors_euro)} du portefeuille est exposé hors zone euro. `
          + (total ? `Le change explique ${pct(part(a.effet_change))} du gain latent.` : '')
        : 'Portefeuille entièrement en euros : aucun effet de change.'}
    </div>
    ${d.message ? `<div class="chart-hint" style="color:var(--yellow)">${esc(d.message)}</div>` : ''}`;

  el('analyseDevises').innerHTML = `
    <thead><tr>
      <th ${TH}>Devise</th><th ${TH} style="text-align:right">Valorisation</th>
      <th ${TH} style="text-align:right">Poids</th>
      <th ${TH} style="text-align:right">+/- latent</th>
      <th ${TH} style="text-align:right">Lignes</th>
    </tr></thead><tbody>` +
    d.devises.map(x => `<tr>
      <td ${TD}><span class="dot-legend" style="background:${couleur(x.devise)}"></span>${esc(x.devise)}</td>
      <td ${TD} style="text-align:right">${fmt(x.valorisation)}</td>
      <td ${TD} style="text-align:right;font-weight:600">${pct(x.poids)}</td>
      <td ${TD} style="text-align:right" class="${cls(x.pv_latent)}">${fmt(x.pv_latent)}</td>
      <td ${TD} style="text-align:right">${x.nb_positions}</td>
    </tr>`).join('') + '</tbody>';
}

// ══════════════════════════════════════════════════════════════
// CONTRIBUTION À LA PERFORMANCE
// ══════════════════════════════════════════════════════════════
function renderContributions(c) {
  if (!c || !c.lignes?.length) {
    el('analyseContributions').innerHTML = '<div class="table-empty">Aucun prix de revient connu.</div>';
    destroyChart('chartContributions');
    return;
  }

  // Dix plus grandes contributions en valeur absolue, pour que les lignes qui
  // ont coûté apparaissent à côté de celles qui ont rapporté.
  const lignes = [...c.lignes]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 10)
    .sort((a, b) => b.contribution - a.contribution);

  makeChart('chartContributions', {
    type: 'bar',
    data: {
      labels: lignes.map(l => l.nom.length > 22 ? l.nom.slice(0, 22) + '…' : l.nom),
      datasets: [{
        label: 'Contribution à la performance',
        data: lignes.map(l => +(l.contribution * 100).toFixed(2)),
        backgroundColor: lignes.map(l => l.contribution >= 0 ? 'rgba(63,185,80,.75)' : 'rgba(248,81,73,.75)'),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${pts(lignes[ctx.dataIndex].contribution)} de performance`,
            afterLabel: ctx => {
              const l = lignes[ctx.dataIndex];
              return `Performance ${pct(l.performance)} · poids ${pct(l.poids_investi)} · ${fmt(l.pv_latent)}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: v => v + ' pts' } },
        y: { grid: { display: false }, ticks: { color: chartColors().muted, font: { size: 11 } } },
      },
    },
  });

  el('analyseContributions').innerHTML = `
    <thead><tr>
      <th ${TH}>Position</th><th ${TH}>Compte</th>
      <th ${TH} style="text-align:right">Performance</th>
      <th ${TH} style="text-align:right">Poids investi</th>
      <th ${TH} style="text-align:right">+/- latent</th>
      <th ${TH} style="text-align:right">Contribution</th>
    </tr></thead><tbody>` +
    c.lignes.map(l => `<tr>
      <td ${TD}>${esc(l.nom)}</td>
      <td ${TD}>${badgeType(l.compte_type)} ${esc(l.compte)}</td>
      <td ${TD} style="text-align:right" class="${cls(l.performance)}">${pct(l.performance)}</td>
      <td ${TD} style="text-align:right">${pct(l.poids_investi)}</td>
      <td ${TD} style="text-align:right" class="${cls(l.pv_latent)}">${fmt(l.pv_latent)}</td>
      <td ${TD} style="text-align:right;font-weight:700" class="${cls(l.contribution)}">${pts(l.contribution)}</td>
    </tr>`).join('') +
    `<tr class="tfoot"><td ${TD} colspan="5">Total — égal à la performance du portefeuille</td>
     <td ${TD} style="text-align:right;font-weight:700" class="${cls(c.total_points)}">${pts(c.total_points)}</td></tr>` +
    '</tbody>';
}

// ══════════════════════════════════════════════════════════════
// RÉPARTITION PAR CLASSE D'ACTIFS
// ══════════════════════════════════════════════════════════════
function renderClasses(rc) {
  const actives = (rc?.classes || []).filter(c => c.valorisation > 0);
  if (!actives.length) {
    el('analyseClasses').innerHTML =
      '<div class="table-empty">Aucune classe d\'actifs renseignée — le champ « Classe d\'actifs » '
      + 'd\'une position alimente cette vue et l\'onglet Rebalancing.</div>';
    destroyChart('chartClasses');
    return;
  }

  makeChart('chartClasses', {
    type: 'doughnut',
    data: {
      labels: actives.map(c => c.label),
      datasets: [{
        data: actives.map(c => c.valorisation),
        backgroundColor: actives.map(c => c.couleur),
        borderWidth: 2, borderColor: 'transparent', hoverOffset: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: ctx => ` ${fmtChart(ctx.raw)} (${(ctx.raw / rc.total * 100).toFixed(1)} %)` } },
      },
    },
  });

  el('analyseClasses').innerHTML = `
    <thead><tr>
      <th ${TH}>Classe d'actifs</th>
      <th ${TH} style="text-align:right">Valorisation</th>
      <th ${TH} style="text-align:right">Poids</th>
      <th ${TH} style="text-align:right">+/- latent</th>
      <th ${TH} style="text-align:right">Lignes</th>
    </tr></thead><tbody>` +
    actives.map(c => `<tr>
      <td ${TD}><span class="dot-legend" style="background:${c.couleur}"></span>${esc(c.label)}</td>
      <td ${TD} style="text-align:right">${fmt(c.valorisation)}</td>
      <td ${TD} style="text-align:right;font-weight:600">${pct(c.poids)}</td>
      <td ${TD} style="text-align:right" class="${cls(c.pv_latent)}">${fmt(c.pv_latent)}</td>
      <td ${TD} style="text-align:right">${c.nb_positions}</td>
    </tr>`).join('') + '</tbody>';
}
