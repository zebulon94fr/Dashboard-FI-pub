// Onglet Analyse : risque, concentration, exposition aux devises, contribution
// à la performance, décomposition du risque et comparaison aux indices. Toutes
// ces mesures sont calculées sur des rendements corrigés des flux.
//
// Trois appels, délibérément séparés : /api/analyse et /api/risque lisent la
// base et répondent tout de suite, /api/suivi télécharge les indices et peut
// prendre quelques secondes. Le dernier ne doit donc pas retenir les deux
// premiers, et son échec ne doit pas vider la page.
import { Store } from './state.js';
import { api } from './api.js';
import { fmt, fmtP, cls, esc, kpiCard, badgeType, destroyChart, makeChart, messageCanvas,
         fmtChart } from './core.js';
import { chartColors, cssVar } from './theme.js';

let periode = 365;
let DONNEES = null;

const el = id => document.getElementById(id);

/**
 * Nombre décimal borné, en notation française.
 *
 * `toFixed` bascule en notation exponentielle au-delà de 1e21 : un ratio de
 * Sharpe aberrant s'affichait « 1,1948150642436363e+48 ». Intl s'en tient à des
 * chiffres, et au-delà d'un seuil absurde on renonce plutôt que d'afficher une
 * ligne de digits qui ne veut rien dire.
 */
function nb(valeur, decimales = 1) {
  if (valeur == null || !Number.isFinite(valeur)) return '—';
  if (Math.abs(valeur) >= 1e9) return '—';
  return new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: decimales, maximumFractionDigits: decimales,
  }).format(valeur);
}

const pct = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : `${nb(v * 100, d)} %`;
const pts = v => v == null || !Number.isFinite(v)
  ? '—' : `${v >= 0 ? '+' : ''}${nb(v * 100, 2)} pts`;

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

  chargerRisquePositions();
  chargerSuivi();
}

// ══════════════════════════════════════════════════════════════
// RISQUE
// ══════════════════════════════════════════════════════════════
function renderRisque(r) {
  const dd = r.drawdown || {};
  const note = el('analyseNote');

  const seances = `${r.nb_observations} séance${r.nb_observations > 1 ? 's' : ''} observée${r.nb_observations > 1 ? 's' : ''}`;

  el('analyseCards').innerHTML =
    kpiCard('Volatilité annualisée', pct(r.volatilite),
      r.annualise ? seances : 'historique trop court', 'neu') +
    kpiCard('Perte maximale', pct(dd.drawdown),
      dd.date_creux ? `creux le ${dd.date_creux}` : '', dd.drawdown ? 'neg' : 'neu') +
    // Tant que l'historique est trop court pour annualiser, on montre la
    // performance de la période : elle, au moins, veut dire quelque chose.
    (r.annualise
      ? kpiCard('Performance annualisée', pct(r.perf_annualisee), 'hors versements', cls(r.perf_annualisee))
      : kpiCard('Performance de la période', pct(r.perf_periode), `sur ${seances}`, cls(r.perf_periode))) +
    kpiCard('Ratio de Sharpe', nb(r.sharpe, 2),
      r.annualise ? `taux sans risque ${pct(r.taux_sans_risque)}` : 'historique trop court', cls(r.sharpe));

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

// ══════════════════════════════════════════════════════════════
// D'OÙ VIENT LE RISQUE
// ══════════════════════════════════════════════════════════════
/** Couleur de série, lue dans le thème courant (voir --serie-* dans style.css). */
const COULEUR_CAPITAL = () => cssVar('--serie-capital');
const COULEUR_RISQUE = () => cssVar('--serie-risque');

/** Teinte posée en transparence : l'intensité suit la force, pas le signe. */
function teinte(hex, alpha) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

async function chargerRisquePositions() {
  const zone = el('analyseRisque');
  if (!zone) return;
  let d;
  try {
    d = await api.getRisque(periode);
  } catch (e) {
    el('analyseRisqueKpis').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }
  renderRisquePositions(d);
}

function renderRisquePositions(d) {
  const note = el('analyseRisqueNote');
  note.innerHTML = d.message ? esc(d.message) : '';
  note.style.display = d.message ? '' : 'none';

  if (!d.lignes.length) {
    // Un graphique vide sans un mot est indiscernable d'un graphique cassé.
    // L'explication complète va dans l'encadré du haut, et chaque boîte
    // affiche là où on la regarde de quoi comprendre qu'elle se remplira.
    el('analyseRisqueKpis').innerHTML = '';
    note.innerHTML = esc(d.message || 'Mesure indisponible.');
    note.style.display = '';

    // On compte les journées **enregistrées**, pas les rendements exploitables :
    // ceux-ci tombent à zéro dès que deux lignes n'ont pas de journée commune,
    // et annoncer « aucune clôture » sur une base qui en contient quatre-vingts
    // ferait douter de la mesure autant que de la base.
    const attendu = d.minimum_observations || 20;
    const jours = d.jours_connus || 0;
    const avancement = jours
      ? `${jours} journée${jours > 1 ? 's' : ''} enregistrée${jours > 1 ? 's' : ''} sur les ${attendu} nécessaires`
      : 'Aucune clôture quotidienne enregistrée pour l\'instant';

    destroyChart('chartRisque');
    const canvas = el('chartRisque');
    if (canvas) messageCanvas(canvas, avancement);

    el('analyseRisque').innerHTML =
      `<tbody><tr><td class="table-empty">${esc(avancement)} — voir l'explication ci-dessus.</td></tr></tbody>`;
    el('analyseCorrelations').innerHTML =
      `<div class="table-empty">${esc(avancement)}. Les corrélations apparaîtront en même temps
       que la contribution au risque.</div>`;
    return;
  }

  el('analyseRisqueKpis').innerHTML =
    kpiCard('Volatilité du portefeuille', pct(d.volatilite_portefeuille),
      `${d.nb_observations} journée(s) exploitée(s)`, 'neu') +
    kpiCard('Si tout bougeait ensemble', pct(d.volatilite_moyenne_ponderee),
      'moyenne pondérée des lignes', 'neu') +
    kpiCard('Ratio de diversification',
      d.ratio_diversification == null ? '—' : nb(d.ratio_diversification, 2),
      d.ratio_diversification > 1 ? 'le mélange amortit' : 'les lignes bougent ensemble',
      d.ratio_diversification > 1.2 ? 'pos' : 'neu') +
    kpiCard('Portefeuille couvert', pct(d.couverture),
      d.ecartees.length ? `${d.ecartees.length} ligne(s) écartée(s)` : 'toutes les lignes',
      d.couverture < 0.9 ? 'neg' : 'neu');

  // Dix lignes par part de risque en valeur absolue : une ligne qui amortit le
  // portefeuille mérite d'apparaître autant qu'une ligne qui l'agite.
  const lignes = [...d.lignes]
    .sort((a, b) => Math.abs(b.part_risque) - Math.abs(a.part_risque))
    .slice(0, 10)
    .sort((a, b) => b.part_risque - a.part_risque);

  makeChart('chartRisque', {
    type: 'bar',
    data: {
      labels: lignes.map(l => l.nom.length > 22 ? l.nom.slice(0, 22) + '…' : l.nom),
      datasets: [
        {
          label: 'Part du capital',
          data: lignes.map(l => +(l.poids * 100).toFixed(2)),
          backgroundColor: COULEUR_CAPITAL(), borderRadius: 4,
          borderColor: cssVar('--surface'), borderWidth: 2,
        },
        {
          label: 'Part du risque',
          data: lignes.map(l => +(l.part_risque * 100).toFixed(2)),
          backgroundColor: COULEUR_RISQUE(), borderRadius: 4,
          borderColor: cssVar('--surface'), borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {
        legend: { position: 'top', labels: { color: chartColors().muted, boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label} : ${nb(ctx.raw, 1)} %`,
            afterLabel: ctx => {
              const l = lignes[ctx.dataIndex];
              return `Volatilité ${pct(l.volatilite)} · β ${nb(l.beta, 2)} · ${fmt(l.valorisation)}`;
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

  el('analyseRisque').innerHTML = `
    <thead><tr>
      <th ${TH}>Position</th><th ${TH}>Compte</th>
      <th ${TH} style="text-align:right">Poids</th>
      <th ${TH} style="text-align:right">Volatilité</th>
      <th ${TH} style="text-align:right" title="De combien la ligne amplifie le portefeuille">β</th>
      <th ${TH} style="text-align:right">Part du risque</th>
      <th ${TH} style="text-align:right">Contribution</th>
    </tr></thead><tbody>` +
    d.lignes.map(l => `<tr>
      <td ${TD}>${esc(l.nom)}${l.part_marche < 0.5
        ? ' <span class="tag tag-mini" title="Cours saisi à la main : volatilité sous-estimée">cours saisi</span>' : ''}</td>
      <td ${TD}>${badgeType(l.compte_type)} ${esc(l.compte)}</td>
      <td ${TD} style="text-align:right">${pct(l.poids)}</td>
      <td ${TD} style="text-align:right">${pct(l.volatilite)}</td>
      <td ${TD} style="text-align:right">${nb(l.beta, 2)}</td>
      <td ${TD} style="text-align:right;font-weight:700" class="${l.part_risque < 0 ? 'pos' : ''}">${pct(l.part_risque)}</td>
      <td ${TD} style="text-align:right">${pct(l.contribution)}</td>
    </tr>`).join('') +
    `<tr class="tfoot">
       <td ${TD} colspan="5">Total — la somme des contributions est la volatilité du portefeuille</td>
       <td ${TD} style="text-align:right;font-weight:700">${pct(
         d.lignes.reduce((a, l) => a + l.part_risque, 0))}</td>
       <td ${TD} style="text-align:right;font-weight:700">${pct(d.volatilite_portefeuille)}</td>
     </tr></tbody>`;

  renderCorrelations(d);
}

function renderCorrelations(d) {
  const zone = el('analyseCorrelations');
  const c = d.correlations;

  const ecartees = d.ecartees.length
    ? `<div class="chart-hint" style="margin-top:10px;color:var(--yellow)">
         Écartées faute d'historique continu : ${d.ecartees
           .map(e => `<strong>${esc(e.nom)}</strong> (${esc(e.motif)})`).join(', ')}.
         La mesure porte sur ${pct(d.couverture)} du portefeuille.
       </div>`
    : '';

  if (!c) {
    zone.innerHTML = '<div class="table-empty">Deux lignes au minimum sont nécessaires '
      + 'pour une corrélation.</div>' + ecartees;
    return;
  }

  const cellule = (valeur, a, b) => {
    if (valeur == null) {
      return `<td title="Corrélation indéfinie : ${esc(b)} n'a pas bougé sur la période">—</td>`;
    }
    const pole = valeur >= 0 ? COULEUR_RISQUE() : COULEUR_CAPITAL();
    return `<td style="background:${teinte(pole, Math.min(0.6, Math.abs(valeur) * 0.6))}"
      title="${esc(a)} / ${esc(b)} : ${nb(valeur, 2)}">${nb(valeur, 2)}</td>`;
  };

  const court = nom => nom.length > 18 ? nom.slice(0, 18) + '…' : nom;

  zone.innerHTML = `
    <div class="matrice-wrap"><table class="matrice">
      <thead><tr><th></th>${c.noms.map(n =>
        `<th title="${esc(n)}">${esc(court(n))}</th>`).join('')}</tr></thead>
      <tbody>${c.matrice.map((rangee, i) => `<tr>
        <th class="matrice-ligne" title="${esc(c.noms[i])}">${esc(court(c.noms[i]))}</th>
        ${rangee.map((valeur, j) => i === j
          ? '<td class="matrice-diagonale">1,00</td>'
          : cellule(valeur, c.noms[i], c.noms[j])).join('')}
      </tr>`).join('')}</tbody>
    </table></div>
    <div class="chart-hint" style="text-align:left;margin-top:10px">
      <span class="dot-legend" style="background:${COULEUR_RISQUE()}"></span>
      Les deux lignes montent et descendent ensemble : elles ne se diversifient pas.
      &nbsp;&nbsp;
      <span class="dot-legend" style="background:${COULEUR_CAPITAL()}"></span>
      Elles vont en sens inverse : l'une amortit l'autre.
      La couleur donne la force, le chiffre la précision.
    </div>
    ${c.plus_correlees.length ? `
      <div class="fisc-line" style="margin-top:10px">
        <span>Les plus redondantes</span>
        <span>${c.plus_correlees.slice(0, 3).map(p =>
          `${esc(p.a)} / ${esc(p.b)} <strong>${nb(p.correlation, 2)}</strong>`).join(' · ')}</span>
      </div>
      <div class="fisc-line">
        <span>Les plus complémentaires</span>
        <span>${c.moins_correlees.slice(0, 3).map(p =>
          `${esc(p.a)} / ${esc(p.b)} <strong>${nb(p.correlation, 2)}</strong>`).join(' · ')}</span>
      </div>` : ''}
    <div class="chart-hint" style="text-align:left">
      ${c.nb_lignes} plus grosses lignes sur ${c.total_lignes} mesurées.
    </div>
    ${ecartees}`;
}

// ══════════════════════════════════════════════════════════════
// FACE AUX INDICES
// ══════════════════════════════════════════════════════════════
async function chargerSuivi() {
  const zone = el('analyseSuivi');
  if (!zone) return;
  zone.innerHTML = '<div class="chart-hint">Chargement des indices…</div>';
  let d;
  try {
    d = await api.getSuivi(periode);
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  if (!d.indices?.length) {
    zone.innerHTML = `<div class="table-empty">${esc(d.message || d.error
      || 'Comparaison indisponible.')}</div>`;
    return;
  }

  // Le signe de l'alpha et de l'écart se lit en couleur ; le bêta et la
  // captation sont des amplitudes, qui n'ont ni bon ni mauvais sens.
  zone.innerHTML = `
    <table style="width:100%;font-size:13px;border-collapse:collapse">
      <thead><tr>
        <th ${TH}>Indice</th>
        <th ${TH} style="text-align:right" title="De combien le portefeuille amplifie l'indice">β</th>
        <th ${TH} style="text-align:right" title="Ce qui reste quand l'exposition à l'indice est retirée">Alpha</th>
        <th ${TH} style="text-align:right" title="Dispersion annualisée des écarts quotidiens">Écart de suivi</th>
        <th ${TH} style="text-align:right" title="Performance active rapportée à l'écart de suivi">Ratio d'info.</th>
        <th ${TH} style="text-align:right" title="Part des mouvements du portefeuille que l'indice explique">R²</th>
        <th ${TH} style="text-align:right">Captation ↑ / ↓</th>
        <th ${TH} style="text-align:right">Écart de performance</th>
      </tr></thead>
      <tbody>${d.indices.map(i => `<tr>
        <td ${TD}>${esc(i.nom)}
          <span class="tag tag-mini" title="${i.rendement === 'total'
            ? 'Indice dividendes réinvestis : comparable à votre portefeuille'
            : 'Indice de prix : il ignore les dividendes que vous encaissez'}">${
            i.rendement === 'total' ? 'div. réinvestis' : 'hors dividendes'}</span></td>
        <td ${TD} style="text-align:right;font-weight:600">${nb(i.beta, 2)}</td>
        <td ${TD} style="text-align:right" class="${cls(i.alpha)}">${pct(i.alpha)}</td>
        <td ${TD} style="text-align:right">${pct(i.tracking_error)}</td>
        <td ${TD} style="text-align:right" class="${cls(i.ratio_information)}">${nb(i.ratio_information, 2)}</td>
        <td ${TD} style="text-align:right">${pct(i.r2)}</td>
        <td ${TD} style="text-align:right">${pct(i.capture_hausse)} / ${pct(i.capture_baisse)}</td>
        <td ${TD} style="text-align:right;font-weight:700" class="${cls(i.ecart)}">${pct(i.ecart)}</td>
      </tr>`).join('')}</tbody>
    </table>
    <div class="chart-hint" style="text-align:left;margin-top:10px">
      Sur ${d.nb_observations} journée(s) communes au portefeuille et aux indices.
      Un bêta supérieur à 1 veut dire que vous amplifiez l'indice : une performance
      supérieure est alors normale, et c'est l'alpha qui dit si elle est méritée.
      Une captation de 120 % à la hausse et de 80 % à la baisse décrit un portefeuille
      qui profite des montées sans subir toute la descente — ce que le bêta, moyenne
      des deux, ne distingue pas.
    </div>
    ${d.message ? `<div class="chart-hint" style="text-align:left;color:var(--yellow)">${esc(d.message)}</div>` : ''}
    ${d.ignores?.length ? `<div class="chart-hint" style="text-align:left">Indices écartés :
      ${d.ignores.map(esc).join(', ')}.</div>` : ''}`;
}
