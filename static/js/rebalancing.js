// Rééquilibrage par classe d'actifs. Une enveloppe n'est pas une classe
// d'actifs : les cibles se règlent ici toutes enveloppes confondues, et la
// répartition par compte reste consultable en second rideau.
import { Store } from './state.js';
import { api } from './api.js';
import { fmt, fmtP, cls, esc, kpiCard, badgeType, emptyState, destroyChart, makeChart } from './core.js';
import { chartColors } from './theme.js';

let cibles = {};        // {classe: pourcentage} en cours d'édition
let DONNEES = null;     // dernière réponse /api/rebalancing

const el = id => document.getElementById(id);
const euro = v => Math.round(v).toLocaleString('fr-FR') + ' €';
const pct = (v, d = 1) => v == null ? '—' : v.toFixed(d).replace('.', ',') + ' %';

const classes = () => Store.CLASSES || [];

export async function renderRebalancing() {
  if (!classes().length) {
    try {
      Store.CLASSES = (await api.getClasses()).catalogue || [];
    } catch { /* le catalogue arrive au prochain chargement */ }
  }
  await rbCalculer(true);
}

/** Interroge le serveur puis redessine tout l'onglet. */
export async function rbCalculer(rechargerCibles = false) {
  const apport = parseFloat((el('rbApport')?.value || '0').replace(',', '.')) || 0;
  const bande = parseFloat(el('rbBande')?.value || '0.25') || 0.25;
  const ordreMin = parseFloat((el('rbOrdreMin')?.value || '100').replace(',', '.')) || 0;

  try {
    DONNEES = await api.getRebalancing({ apport, bande, ordre_min: ordreMin });
  } catch (e) {
    el('rbKpis').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  if (!DONNEES.classes.length && !DONNEES.total) {
    el('rbKpis').innerHTML = '';
    el('rbCiblesForm').innerHTML = emptyState(
      'Rien à équilibrer pour l\'instant',
      'Créez un compte et quelques positions : leur classe d\'actifs alimente cette page.',
      '<button class="btn primary" onclick="openAccountModal()">+ Créer un compte</button>');
    el('rbTableEcarts').innerHTML = '';
    el('rbOrdres').innerHTML = '';
    destroyChart('rbChartAlloc');
    return;
  }

  if (rechargerCibles) {
    cibles = Object.fromEntries(DONNEES.classes.map(c => [c.classe, c.cible_pct]));
    renderCiblesForm();
  }

  renderKpis();
  renderGraphique();
  renderTableEcarts();
  renderMouvements();
}

// ══════════════════════════════════════════════════════════════
// CIBLES
// ══════════════════════════════════════════════════════════════
function renderCiblesForm() {
  const connues = new Set(DONNEES.classes.map(c => c.classe));
  const liste = classes().filter(c => connues.has(c.id) || (cibles[c.id] || 0) > 0
                                      || c.id !== 'autre');

  el('rbCiblesForm').innerHTML = liste.map(c => `
    <div class="rb-row">
      <span class="rb-label"><span class="dot-legend" style="background:${c.couleur}"></span>${esc(c.label)}</span>
      <input type="range" min="0" max="100" step="1" value="${cibles[c.id] || 0}"
             id="rb_slider_${c.id}" oninput="rbSliderChange('${c.id}', this.value)"
             style="accent-color:${c.couleur}">
      <span class="rb-value" id="rb_val_${c.id}" style="color:${c.couleur}">${cibles[c.id] || 0} %</span>
      <span class="rb-real" id="rb_reel_${c.id}"></span>
    </div>`).join('');

  majReels();
  majTotalCibles();
}

function majReels() {
  for (const c of DONNEES.classes) {
    const zone = el(`rb_reel_${c.classe}`);
    if (zone) zone.textContent = `réel : ${pct(c.poids)}`;
  }
}

function majTotalCibles() {
  const total = Object.values(cibles).reduce((s, v) => s + (v || 0), 0);
  const element = el('rbTotalCibles');
  element.textContent = `${total} %`;
  element.className = Math.abs(total - 100) <= 0.01 ? 'pos' : 'neg';
  el('rbCiblesHint').textContent = Math.abs(total - 100) <= 0.01
    ? '' : 'Tant que les cibles ne totalisent pas 100 %, les écarts ne veulent rien dire.';
}

export function rbSliderChange(classe, valeur) {
  cibles[classe] = parseInt(valeur) || 0;
  el(`rb_val_${classe}`).textContent = `${cibles[classe]} %`;
  majTotalCibles();
}

export async function rbSauvegarderCibles() {
  const bouton = el('rbSaveBtn');
  const libelle = bouton?.textContent;
  try {
    await api.saveCiblesClasses(cibles);
    if (bouton) {
      bouton.textContent = '✓ Enregistré';
      setTimeout(() => { bouton.textContent = libelle; }, 1500);
    }
    await rbCalculer();
  } catch (e) {
    alert('Sauvegarde impossible : ' + e.message);
  }
}

// ══════════════════════════════════════════════════════════════
// AFFICHAGE
// ══════════════════════════════════════════════════════════════
function renderKpis() {
  const r = DONNEES.resume;
  el('rbKpis').innerHTML =
    kpiCard('Patrimoine total', fmt(DONNEES.total),
      DONNEES.apport ? `+ ${euro(DONNEES.apport)} d'apport` : 'sans apport', 'neu') +
    kpiCard('Classes hors bande', `${r.nb_hors_bande}`,
      r.nb_hors_bande ? 'à rééquilibrer' : 'tout est dans les clous',
      r.nb_hors_bande ? 'neg' : 'pos') +
    kpiCard('Écart maximum', `${r.derive_max.toFixed(1).replace('.', ',')} pts`, 'par rapport à la cible', 'neu') +
    kpiCard('À vendre', fmt(r.a_vendre),
      r.a_vendre ? 'après affectation de l\'apport' : 'aucune vente nécessaire',
      r.a_vendre ? 'neg' : 'pos');
}

function renderGraphique() {
  const liste = DONNEES.classes;
  makeChart('rbChartAlloc', {
    type: 'bar',
    data: {
      labels: liste.map(c => c.label),
      datasets: [
        {
          label: 'Réel',
          data: liste.map(c => c.poids),
          backgroundColor: liste.map(c => c.couleur + '99'),
          borderRadius: 4,
        },
        {
          label: 'Cible',
          data: liste.map(c => c.cible_pct),
          backgroundColor: 'rgba(0,0,0,0)',
          borderColor: liste.map(c => c.couleur),
          borderWidth: 2, borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label} : ${pct(ctx.raw)}` } },
      },
      scales: {
        x: { ticks: { color: chartColors().muted, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { color: chartColors().muted, font: { size: 10 }, callback: v => v + ' %' },
             grid: { color: chartColors().grid } },
      },
    },
  });
}

const TH = 'style="padding:10px 14px;text-align:left;color:var(--muted);font-weight:500;white-space:nowrap;border-bottom:1px solid var(--border);font-size:12px"';
const TD = 'style="padding:10px 14px;border-bottom:1px solid var(--border);white-space:nowrap;font-size:13px"';

function renderTableEcarts() {
  const statuts = {
    equilibre: ['✓ Dans la bande', 'pos'],
    sous_pondere: ['↑ Sous-pondéré', 'neg'],
    sur_pondere: ['↓ Sur-pondéré', 'neg'],
  };

  el('rbTableEcarts').innerHTML = `<thead><tr>
      <th ${TH}>Classe d'actifs</th>
      <th ${TH} style="text-align:right">Valeur actuelle</th>
      <th ${TH} style="text-align:right">Réel</th>
      <th ${TH} style="text-align:right">Cible</th>
      <th ${TH} style="text-align:right">Bande</th>
      <th ${TH} style="text-align:right">Écart</th>
      <th ${TH} style="text-align:right">Écart (€)</th>
      <th ${TH} style="text-align:center">Statut</th>
    </tr></thead><tbody>` +
    DONNEES.classes.map(c => {
      const [libelle, classe] = statuts[c.statut];
      return `<tr>
        <td ${TD}><span class="dot-legend" style="background:${c.couleur}"></span>${esc(c.label)}</td>
        <td ${TD} style="text-align:right">${fmt(c.valorisation)}</td>
        <td ${TD} style="text-align:right">${pct(c.poids)}</td>
        <td ${TD} style="text-align:right;font-weight:600">${pct(c.cible_pct, 0)}</td>
        <td ${TD} style="text-align:right" class="muted">±${c.bande.toFixed(2).replace('.', ',')}</td>
        <td ${TD} style="text-align:right" class="${c.ecart_pts > 0 ? 'pos' : 'neg'}">${
          (c.ecart_pts > 0 ? '+' : '') + c.ecart_pts.toFixed(1).replace('.', ',')} pts</td>
        <td ${TD} style="text-align:right" class="${c.ecart_eur > 0 ? 'pos' : 'neg'}">${
          (c.ecart_eur > 0 ? '+' : '') + euro(c.ecart_eur)}</td>
        <td ${TD} style="text-align:center" class="${classe}">${libelle}</td>
      </tr>`;
    }).join('') + '</tbody>';
}

function renderMouvements() {
  const conteneur = el('rbOrdres');
  const info = el('rbOrdresInfo');
  const r = DONNEES.resume;

  const aFinancer = DONNEES.apports.filter(a => a.reste_a_financer > 0 || a.apport_affecte > 0);

  if (!aFinancer.length && !DONNEES.ventes.length) {
    conteneur.innerHTML = `<div class="table-empty">✓ Toutes les classes sont dans leur bande de tolérance —
      aucun arbitrage nécessaire. La bande vaut le plus petit de 5 points ou 25 % de la cible.</div>`;
    info.textContent = '';
    return;
  }
  info.textContent = `${r.nb_hors_bande} classe${r.nb_hors_bande > 1 ? 's' : ''} hors bande`;

  const carteApport = a => `
    <div class="rb-card" style="border-left-color:${a.couleur}">
      <div class="rb-card-head">
        <span><span class="dot-legend" style="background:${a.couleur}"></span>${esc(a.label)}</span>
        <span class="pos" style="font-size:16px;font-weight:700">+${euro(a.ecart_eur)}</span>
      </div>
      <div class="rb-card-body">
        Réel <strong>${pct(a.poids)}</strong> → cible <strong>${pct(a.cible_pct, 0)}</strong><br>
        ${euro(a.valorisation)} → objectif ${euro(a.montant_cible)}
      </div>
      ${a.apport_affecte > 0
        ? `<div class="rb-card-hint pos">Apport affecté : ${euro(a.apport_affecte)}${
            a.reste_a_financer > 0 ? ` — reste ${euro(a.reste_a_financer)} à financer` : ' — entièrement couvert'}</div>`
        : '<div class="rb-card-hint">À financer par un apport ou par un allègement.</div>'}
    </div>`;

  const carteVente = v => `
    <div class="rb-card" style="border-left-color:${v.couleur}">
      <div class="rb-card-head">
        <span><span class="dot-legend" style="background:${v.couleur}"></span>${esc(v.label)}</span>
        <span class="neg" style="font-size:16px;font-weight:700">−${euro(v.montant)}</span>
      </div>
      <div class="rb-card-body">
        Réel <strong>${pct(v.poids)}</strong> → cible <strong>${pct(v.cible_pct, 0)}</strong><br>
        ${euro(v.valorisation)} → objectif ${euro(v.montant_cible)}
      </div>
      ${v.lignes.length ? `
        <div class="rb-card-hint">Alléger dans cet ordre — le moins coûteux fiscalement d'abord :</div>
        <ol class="rb-lignes">
          ${v.lignes.map(l => `<li>
            <span>${esc(l.nom)} <span class="muted">· ${esc(l.compte)}</span></span>
            <span class="${cls(l.pv_latent)}">${fmt(l.pv_latent)}</span>
            <span class="rb-impot">${l.cout_fiscal > 0 ? `impôt ~${euro(l.cout_fiscal)}` : 'non imposable'}</span>
          </li>`).join('')}
        </ol>
        ${v.lignes[0].avertissement ? `<div class="rb-card-warn">⚠ ${esc(v.lignes[0].avertissement)}</div>` : ''}
      ` : ''}
    </div>`;

  conteneur.innerHTML = `
    <div class="rb-columns">
      <div>
        ${aFinancer.length ? '<div class="rb-col-title pos">Renforcer</div>' : ''}
        ${aFinancer.map(carteApport).join('')}
      </div>
      <div>
        ${DONNEES.ventes.length
          ? '<div class="rb-col-title neg">Alléger</div>' + DONNEES.ventes.map(carteVente).join('')
          : '<div class="table-empty">Aucune vente nécessaire — l\'apport couvre le rééquilibrage.</div>'}
      </div>
    </div>
    <div class="rb-summary">
      <div><div class="rb-summary-label">Besoin total</div><div class="rb-summary-value">${euro(r.besoin_total)}</div></div>
      <div><div class="rb-summary-label">Couvert par l'apport</div><div class="pos rb-summary-value">${euro(r.apport_utilise)}</div></div>
      <div><div class="rb-summary-label">À financer par vente</div><div class="neg rb-summary-value">${euro(r.a_vendre)}</div></div>
      <div><div class="rb-summary-label">Reste non financé</div><div class="rb-summary-value">${euro(r.reste_a_financer)}</div></div>
    </div>
    ${DONNEES.non_classees
      ? `<div class="chart-hint" style="color:var(--yellow)">${DONNEES.non_classees} position(s) sans classe d'actifs :
         elles pèsent dans « Non classé » et faussent l'allocation. Renseignez leur classe dans le formulaire de position.</div>`
      : ''}`;
}
