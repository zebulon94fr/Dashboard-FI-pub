// Projection patrimoniale et indépendance financière.
//
// Trois défauts du modèle précédent sont corrigés ici. Il composait un taux
// annuel fixe, ce qui masque le **risque de séquence** — un rendement moyen de
// 7 % obtenu avec un krach en début de retrait ruine un plan qu'un 7 % linéaire
// faisait tenir. Il ignorait les **frais**, qui coûtent environ un cinquième du
// capital terminal sur vingt-cinq ans. Et il s'arrêtait à l'accumulation, sans
// jamais simuler la **décumulation**, seul moment où le plan peut échouer.
import { Store } from './state.js';
import { api } from './api.js';
import { fmt, fmtP, cls, esc, kpiCard, makeChart, fmtChart, parseNum } from './core.js';
import { chartColors } from './theme.js';

let FI = null;              // dernière réponse /api/fi
let simulationEnCours = false;

const el = id => document.getElementById(id);
const nb = (v, d = 1) => v == null || !Number.isFinite(v) ? '—'
  : new Intl.NumberFormat('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
const pct = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : `${nb(v * 100, d)} %`;

// ══════════════════════════════════════════════════════════════
// PROFIL
// ══════════════════════════════════════════════════════════════
export async function loadSimulation() {
  try {
    FI = await api.getFi();
  } catch (e) {
    el('simCards').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  const r = FI.reglages || {};
  const champs = {
    simDepenses: r.depenses_annuelles, simEpargne: r.epargne_mensuelle,
    simRetrait: r.taux_retrait, simRendement: r.rendement_reel, simHorizon: r.horizon_ans,
  };
  for (const [id, valeur] of Object.entries(champs)) {
    if (el(id) && !el(id).dataset.touche) el(id).value = valeur ?? '';
  }

  renderFI();
  simUpdate();
}

/** Enregistre le profil côté serveur : il sert aussi aux alertes et au résumé. */
export async function saveProfil() {
  const bouton = el('simSaveBtn');
  const libelle = bouton?.textContent;
  try {
    await api.saveReglages({
      depenses_annuelles: parseNum(el('simDepenses').value),
      epargne_mensuelle: parseNum(el('simEpargne').value),
      taux_retrait: parseNum(el('simRetrait').value),
      rendement_reel: parseNum(el('simRendement').value),
      horizon_ans: parseNum(el('simHorizon').value),
    });
    // Les métriques dépendent du portefeuille autant que du profil : on relit.
    FI = await api.getFi();
    if (bouton) {
      bouton.textContent = '✓ Enregistré';
      setTimeout(() => { bouton.textContent = libelle; }, 1500);
    }
    renderFI();
    simUpdate();
  } catch (e) {
    alert('Enregistrement impossible : ' + e.message);
  }
}

export function onProfilChange() {
  // Une saisie en cours ne doit pas être écrasée par un rechargement.
  ['simDepenses', 'simEpargne', 'simRetrait', 'simRendement', 'simHorizon']
    .forEach(id => { if (el(id)) el(id).dataset.touche = '1'; });
  simUpdate();
}

// ══════════════════════════════════════════════════════════════
// MÉTRIQUES D'INDÉPENDANCE
// ══════════════════════════════════════════════════════════════
function renderFI() {
  const p = FI?.patrimoine || {};
  const f = FI?.frais || {};

  // Le patrimoine net n'a de sens affiché que si un passif existe.
  const cartesPatrimoine =
    kpiCard('Patrimoine net', fmt(p.patrimoine_net),
      p.a_passif ? `${fmt(p.actif_brut)} d'actifs − ${fmt(p.passif)} de dettes` : 'aucun passif enregistré', 'neu') +
    kpiCard('Capital financier', fmt(p.capital_fi),
      'ce qui finance l\'indépendance', 'neu') +
    kpiCard('Frais annuels', fmt(f.cout_annuel),
      f.taux_moyen ? `${pct(f.taux_moyen, 2)} du capital financier` : 'aucun frais renseigné',
      f.cout_annuel ? 'neg' : 'neu');

  if (!FI?.capital_cible) {
    el('simCards').innerHTML = cartesPatrimoine;
    el('simFiNote').textContent = FI?.message || '';
    el('simFiNote').style.display = FI?.message ? '' : 'none';
    el('simFiDetail').innerHTML = '';
    return;
  }

  el('simFiNote').textContent = FI.message || '';
  el('simFiNote').style.display = FI.message ? '' : 'none';

  el('simCards').innerHTML = cartesPatrimoine +
    kpiCard('Capital-cible', fmt(FI.capital_cible),
      `${fmt(FI.reglages.depenses_annuelles)} / an à ${nb(FI.reglages.taux_retrait, 1)} %`, 'neu') +
    kpiCard('Couverture', pct(FI.couverture),
      `${fmt(FI.revenu_actuel_mensuel)} par mois sur ${fmt(FI.depenses_mensuelles)} visés`,
      FI.couverture >= 1 ? 'pos' : 'neu') +
    kpiCard('Indépendance', FI.annees_restantes == null ? '—'
      : FI.annees_restantes === 0 ? 'atteinte' : `${nb(FI.annees_restantes, 1)} ans`,
      FI.date_independance ? `vers ${new Date(FI.date_independance).toLocaleDateString('fr-FR')}` : '',
      FI.annees_restantes === 0 ? 'pos' : 'neu') +
    kpiCard('Taux d\'épargne', pct(FI.taux_epargne),
      `${fmt(FI.epargne_annuelle)} par an`, 'neu');

  const cf = FI.coast_fi || {};
  el('simFiDetail').innerHTML = `
    <div class="fisc-line"><span>Il manque pour être indépendant</span>
      <span class="${FI.manque ? 'neg' : 'pos'}">${fmt(FI.manque)}</span></div>
    <div class="fisc-line"><span>Rendement retenu, net des frais mesurés</span>
      <span>${pct(FI.rendement_retenu, 2)}</span></div>
    <div class="fisc-line"><span>Effet de 200 € d'épargne mensuelle en plus</span>
      <span class="pos">${FI.gain_mois_si_plus_200 ? `−${FI.gain_mois_si_plus_200} mois` : '—'}</span></div>
    <div class="fisc-line"><span>Coast FI sur ${cf.horizon_ans} ans
      <span class="muted">— capital à partir duquel ne plus rien verser suffit</span></span>
      <span class="${cf.atteint ? 'pos' : ''}">${cf.atteint ? '✓ atteint' : fmt(cf.cible)}</span></div>
    ${f.erosion_25_ans ? `<div class="fisc-line"><span>Ce que les frais coûteront sur 25 ans</span>
      <span class="neg">${pct(f.erosion_25_ans)} du capital</span></div>` : ''}`;
}

// ══════════════════════════════════════════════════════════════
// MONTE-CARLO
// ══════════════════════════════════════════════════════════════
/** Tirage normal centré réduit (Box-Muller). */
function normale() {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/**
 * Simule `tirages` trajectoires : accumulation puis décumulation.
 *
 * Les rendements sont tirés mois par mois autour du rendement attendu, avec la
 * volatilité saisie. C'est ce tirage qui fait apparaître le risque de séquence :
 * deux trajectoires de même rendement moyen ne finissent pas au même endroit
 * selon l'ordre dans lequel les bonnes et les mauvaises années se présentent.
 */
export function monteCarlo({ depart, versementMensuel, annees, rendement, volatilite,
                             tirages = 1000, depensesAnnuelles = 0, anneesRetraite = 30 }) {
  const moisAccumulation = Math.max(1, Math.round(annees * 12));
  const moisRetraite = Math.max(0, Math.round(anneesRetraite * 12));
  const sigma = volatilite / Math.sqrt(12);
  // Dérive log-normale : la moyenne arithmétique des rendements dépasse la
  // moyenne géométrique de sigma²/2, il faut le retrancher.
  const mu = Math.log(1 + rendement) / 12 - (sigma * sigma) / 2;

  const parAnnee = Array.from({ length: annees + 1 }, () => []);
  const finales = [];
  let echecs = 0;

  for (let t = 0; t < tirages; t++) {
    let valeur = depart;
    parAnnee[0].push(valeur);

    for (let m = 1; m <= moisAccumulation; m++) {
      valeur = (valeur + versementMensuel) * Math.exp(mu + sigma * normale());
      if (m % 12 === 0 && m / 12 <= annees) parAnnee[m / 12].push(valeur);
    }
    finales.push(valeur);

    // Décumulation : on retire les dépenses, et l'on regarde si le capital tient.
    if (moisRetraite && depensesAnnuelles > 0) {
      let capital = valeur;
      const retraitMensuel = depensesAnnuelles / 12;
      for (let m = 1; m <= moisRetraite; m++) {
        capital = (capital - retraitMensuel) * Math.exp(mu + sigma * normale());
        if (capital <= 0) { echecs++; break; }
      }
    }
  }

  const percentile = (tableau, p) => {
    const trie = [...tableau].sort((a, b) => a - b);
    return trie[Math.min(trie.length - 1, Math.floor(p * trie.length))];
  };

  return {
    p10: parAnnee.map(v => percentile(v, 0.10)),
    p50: parAnnee.map(v => percentile(v, 0.50)),
    p90: parAnnee.map(v => percentile(v, 0.90)),
    finales,
    mediane: percentile(finales, 0.50),
    tirages,
    tauxEchec: moisRetraite && depensesAnnuelles > 0 ? echecs / tirages : null,
    anneesRetraite,
  };
}

// ══════════════════════════════════════════════════════════════
// RENDU DE LA PROJECTION
// ══════════════════════════════════════════════════════════════
export function simUpdate() {
  if (simulationEnCours) return;
  simulationEnCours = true;
  try {
    dessinerProjection();
  } finally {
    simulationEnCours = false;
  }
}

function dessinerProjection() {
  const annees = parseInt(el('simYears').value) || 20;
  const volatilite = (parseFloat(el('simVol').value) || 15) / 100;
  const tirages = parseInt(el('simTirages').value) || 1000;
  const anneesRetraite = parseInt(el('simRetraite').value) || 30;

  const depenses = parseNum(el('simDepenses').value);
  const epargne = parseNum(el('simEpargne').value);
  const tauxRetrait = (parseNum(el('simRetrait').value) || 4) / 100;
  const rendementBrut = (parseNum(el('simRendement').value) || 4) / 100;

  el('simYearsVal').textContent = `${annees} ans`;
  el('simVolVal').textContent = `${nb(volatilite * 100)} %`;
  el('simRetraiteVal').textContent = `${anneesRetraite} ans`;

  // Les frais mesurés sur le portefeuille réel sont retranchés du rendement :
  // c'est ce qui manquait le plus à la projection précédente.
  const fraisTaux = FI?.frais?.taux_moyen || 0;
  const rendement = rendementBrut - fraisTaux;
  const depart = FI?.patrimoine?.capital_fi || 0;
  const cible = depenses > 0 && tauxRetrait > 0 ? depenses / tauxRetrait : null;

  const mc = monteCarlo({
    depart, versementMensuel: epargne, annees, rendement, volatilite, tirages,
    depensesAnnuelles: depenses, anneesRetraite,
  });

  const atteint = cible ? mc.finales.filter(v => v >= cible).length / mc.tirages : null;
  const labels = Array.from({ length: annees + 1 }, (_, i) =>
    i === 0 ? 'Auj.' : String(new Date().getFullYear() + i));

  const datasets = [
    {
      label: 'Optimiste (9 cas sur 10 en dessous)', data: mc.p90,
      borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.10)',
      fill: '+1', tension: .3, pointRadius: 0, pointHoverRadius: 5, borderWidth: 1.5, borderDash: [5, 4],
    },
    {
      label: 'Médiane', data: mc.p50,
      borderColor: '#58a6ff', backgroundColor: 'transparent',
      fill: false, tension: .3, pointRadius: 0, pointHoverRadius: 6, borderWidth: 2.5,
    },
    {
      label: 'Pessimiste (1 cas sur 10 en dessous)', data: mc.p10,
      borderColor: '#f85149', backgroundColor: 'transparent',
      fill: false, tension: .3, pointRadius: 0, pointHoverRadius: 5, borderWidth: 1.5, borderDash: [5, 4],
    },
  ];
  if (cible) {
    datasets.push({
      label: 'Capital-cible', data: labels.map(() => cible),
      borderColor: chartColors().muted, backgroundColor: 'transparent',
      fill: false, pointRadius: 0, borderWidth: 1.5, borderDash: [2, 3],
    });
  }

  makeChart('chartSim', {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 14, usePointStyle: true, pointStyle: 'line' } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label} : ${fmtChart(ctx.raw)}` } },
      },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, maxTicksLimit: 10 } },
        y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtChart } },
      },
    },
  });

  const investi = depart + epargne * 12 * annees;
  el('simProjCards').innerHTML =
    kpiCard('Capital médian', fmt(mc.p50[annees]), `dans ${annees} ans`, 'neu') +
    kpiCard('Fourchette', `${fmtChart(mc.p10[annees])} → ${fmtChart(mc.p90[annees])}`,
      '8 trajectoires sur 10', 'neu') +
    kpiCard('Versé au total', fmt(investi),
      epargne > 0 ? `${fmt(epargne)} par mois` : 'sans versement', 'neu') +
    (atteint != null
      ? kpiCard('Objectif atteint', pct(atteint, 0), `sur ${mc.tirages} trajectoires`,
          atteint >= 0.8 ? 'pos' : atteint >= 0.5 ? 'neu' : 'neg')
      : '') +
    (mc.tauxEchec != null
      ? kpiCard('Capital épuisé', pct(mc.tauxEchec, 0),
          `avant ${mc.anneesRetraite} ans de retraits`,
          mc.tauxEchec <= 0.05 ? 'pos' : mc.tauxEchec <= 0.15 ? 'neu' : 'neg')
      : '');

  el('simNote').innerHTML = [
    fraisTaux
      ? `Rendement projeté <strong>${pct(rendement, 2)}</strong> : ${pct(rendementBrut, 2)} attendus
         moins ${pct(fraisTaux, 2)} de frais réellement mesurés sur votre portefeuille.`
      : `Rendement projeté <strong>${pct(rendement, 2)}</strong>. Renseignez les frais de gestion
         de vos comptes et le TER de vos supports pour que la projection les déduise.`,
    mc.tauxEchec != null
      ? `Le taux d'épuisement mesure le <strong>risque de séquence</strong> : la part des
         trajectoires où le capital tombe à zéro avant ${mc.anneesRetraite} ans de retraits.
         Un rendement moyen identique peut réussir ou échouer selon l'ordre dans lequel les
         mauvaises années se présentent — c'est ce qu'une projection à taux constant ne peut
         pas montrer.`
      : `Renseignez vos dépenses annuelles pour simuler aussi la phase de retraits, seule
         étape où un plan peut réellement échouer.`,
    'Les montants sont en euros constants : le rendement saisi est net d\'inflation.',
  ].map(t => `<p>${t}</p>`).join('');

  renderTable(mc, annees, epargne, depart);
}

function renderTable(mc, annees, epargne, depart) {
  const th = 'style="padding:7px 10px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
  const td = 'style="padding:7px 10px;border-bottom:1px solid var(--border)"';

  const lignes = mc.p50.map((valeur, i) => {
    const investiCumule = depart + epargne * 12 * i;
    const gain = valeur - investiCumule;
    return `<tr>
      <td ${td}>${i === 0 ? 'Aujourd\'hui' : `Année ${i}`}</td>
      <td ${td}>${new Date().getFullYear() + i}</td>
      <td ${td} style="text-align:right">${fmt(mc.p10[i])}</td>
      <td ${td} style="text-align:right;font-weight:600">${fmt(valeur)}</td>
      <td ${td} style="text-align:right">${fmt(mc.p90[i])}</td>
      <td ${td} style="text-align:right">${fmt(investiCumule)}</td>
      <td ${td} style="text-align:right" class="${cls(gain)}">${fmt(gain)}</td>
    </tr>`;
  }).join('');

  el('simTable').innerHTML = `<thead><tr>
      <th ${th}>Période</th><th ${th}>Année</th>
      <th ${th} style="text-align:right">Pessimiste</th>
      <th ${th} style="text-align:right">Médiane</th>
      <th ${th} style="text-align:right">Optimiste</th>
      <th ${th} style="text-align:right">Versé</th>
      <th ${th} style="text-align:right">Gain</th>
    </tr></thead><tbody>${lignes}</tbody>`;
}
