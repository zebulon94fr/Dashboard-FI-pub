import { typeInfo, comptes, compteById } from './state.js';
import { fmt, fmtP, cls, kpiCard, esc, emptyState } from './core.js';
import { anciennete, statutFiscal } from './accounts.js';

// Taux en vigueur, alignés sur catalog.py (source unique côté serveur pour les libellés).
const PS = 0.172, PFU_IR = 0.128, PFU = 0.30;
const AV_IR_REDUIT = 0.075;
const AV_ABATTEMENT = { seul: 4600, couple: 9200 };
const CRYPTO_SEUIL_EXONERATION = 305;
const METAUX_FORFAIT = 0.115, METAUX_PV = 0.362;

let compteSelectionne = null;

const el = id => document.getElementById(id);
const euro = v => v == null ? '—'
  : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(Math.round(v)) + ' €';

function ligne(label, valeur, classe = '') {
  const style = 'padding:8px 0;border-bottom:1px solid var(--border)';
  return `<tr>
    <td style="${style};color:var(--muted)">${label}</td>
    <td style="${style};text-align:right;font-weight:600" class="${classe}">${valeur}</td>
  </tr>`;
}

/** Part des gains dans la valorisation — sert au prorata des rachats partiels. */
function ratioGains(compte) {
  if (!compte.valorisation) return 0;
  return Math.max(0, (compte.pv_latent || 0) / compte.valorisation);
}

/** Abattement pour durée de détention des métaux précieux (5 %/an au-delà de 2 ans). */
function abattementMetaux(annees) {
  return Math.min(1, Math.max(0, (annees - 2) * 0.05));
}

/** Taux d'imposition marginal appliqué aux plus-values latentes, par enveloppe. */
export function tauxMarginal(compte) {
  const t = typeInfo(compte.type);
  const atteint = statutFiscal(compte).atteint;
  switch (t.modele_fiscal) {
    case 'pea':    return atteint ? PS : PFU;
    case 'av':     return atteint ? AV_IR_REDUIT + PS : PFU;
    case 'metaux': return METAUX_PV * (1 - abattementMetaux(anciennete(compte) ?? 0));
    case 'per':    return PFU;      // sur la seule quote-part de gains
    default:       return PFU;      // CTO, cryptomonnaies
  }
}

// ══════════════════════════════════════════════════════════════
// RENDU
// ══════════════════════════════════════════════════════════════
export function renderFiscalite() {
  const liste = comptes();
  const onglets = el('fiscTabs');
  const contenu = el('fiscContent');

  if (!liste.length) {
    onglets.innerHTML = '';
    contenu.innerHTML = emptyState(
      'Aucun compte à analyser',
      'La fiscalité affichée dépend du type de vos comptes et de leur date d\'ouverture.',
      '<button class="btn primary" onclick="openAccountModal()">+ Créer un compte</button>');
    return;
  }

  if (!liste.some(c => c.id === compteSelectionne)) compteSelectionne = liste[0].id;

  onglets.innerHTML = liste.map(c => {
    const t = typeInfo(c.type);
    return `<button class="btn ${c.id === compteSelectionne ? 'primary' : ''}"
                    onclick="showFiscTab(${c.id})">${esc(t.icone)} ${esc(c.nom)}</button>`;
  }).join('');

  renderCompteFiscal(compteById(compteSelectionne));
}

export function showFiscTab(accountId) {
  compteSelectionne = Number(accountId);
  renderFiscalite();
}

function renderCompteFiscal(compte) {
  const t = typeInfo(compte.type);
  const statut = statutFiscal(compte);
  const ans = anciennete(compte);
  const positions = compte.positions || [];
  const enGain = positions.filter(p => (p.pv_latent || 0) > 0);
  const enPerte = positions.filter(p => (p.pv_latent || 0) < 0);
  const taux = tauxMarginal(compte);

  const kpis =
    kpiCard('Valorisation', fmt(compte.valorisation)) +
    kpiCard('Montant investi', fmt(compte.investi)) +
    kpiCard('Plus-value latente', fmt(compte.pv_latent), fmtP(compte.pv_pct), cls(compte.pv_pct)) +
    kpiCard('Ancienneté', ans != null ? `${ans.toFixed(1)} ans` : '—', statut.texte, statut.atteint ? 'pos' : 'neu') +
    kpiCard('Taux sur les gains', `${(taux * 100).toFixed(1)} %`, 'estimation à la sortie', 'neu');

  const bandeau = `<div class="callout" style="border-left-color:${t.couleur}">
    <strong>${esc(t.nom_complet || t.label)}</strong> — ${esc(t.resume_fiscal)}
  </div>`;

  const situation = [
    ['Valorisation actuelle', euro(compte.valorisation), ''],
    ['Montant investi', euro(compte.investi), ''],
    ['Plus ou moins-value latente', euro(compte.pv_latent), (compte.pv_latent || 0) >= 0 ? 'pos' : 'neg'],
    ['Performance globale', fmtP(compte.pv_pct), cls(compte.pv_pct)],
    ['Positions en gain', `${enGain.length}`, 'pos'],
    ['Positions en perte', `${enPerte.length}`, 'neg'],
    ['Date d\'ouverture', compte.date_ouverture || 'non renseignée', compte.date_ouverture ? '' : 'neg'],
  ].map(([l, v, c]) => ligne(l, v, c)).join('');

  const regles = (t.regles || []).map(([l, v, c]) => ligne(l, v, c)).join('');

  el('fiscContent').innerHTML = `
    <div class="cards">${kpis}</div>
    ${bandeau}
    <div class="chart-grid" style="margin-bottom:16px">
      <div class="chart-box">
        <div class="chart-title">Règles fiscales — ${esc(t.label)}</div>
        <table class="fisc-table">${regles}</table>
      </div>
      <div class="chart-box">
        <div class="chart-title">Situation actuelle</div>
        <table class="fisc-table">${situation}</table>
      </div>
    </div>
    <div class="chart-box" style="margin-bottom:16px">
      <div class="chart-title">Simulateur de sortie</div>
      ${simulateurHtml(compte)}
      <div id="fiscResultat" class="fisc-result"></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Positions en gain — imposition estimée à la sortie</div>
      <table class="fisc-table">${tableauGains(enGain, taux)}</table>
    </div>`;

  calcFisc();
}

// ══════════════════════════════════════════════════════════════
// SIMULATEUR
// ══════════════════════════════════════════════════════════════
function curseur(id, label, max, valeur, pas = 500) {
  return `<div class="fisc-slider">
    <label>${label}</label>
    <input type="range" id="${id}" min="0" max="${Math.max(pas, max)}" step="${pas}"
           value="${Math.min(valeur, Math.max(pas, max))}" oninput="calcFisc()">
    <span id="${id}Val"></span>
  </div>`;
}

function simulateurHtml(compte) {
  const t = typeInfo(compte.type);
  const valorisation = Math.max(1000, Math.round(compte.valorisation / 500) * 500);
  const gainMax = Math.max(500, Math.round(Math.max(0, compte.pv_latent) / 500) * 500);
  const defautMontant = Math.min(10000, valorisation);
  const defautGain = Math.round(defautMontant * ratioGains(compte));

  let champs = curseur('fiscMontant', t.modele_fiscal === 'metaux' ? 'Montant de la cession' : 'Montant retiré',
    valorisation, defautMontant);

  // L'assurance vie et le PER raisonnent en prorata : le gain est déduit du rachat.
  if (!['av', 'per'].includes(t.modele_fiscal)) {
    champs += curseur('fiscGain', 'Plus-value comprise dans ce montant',
      Math.max(gainMax, defautGain), defautGain);
  }

  if (t.modele_fiscal === 'av') {
    champs += `<div class="fisc-slider">
      <label>Situation du foyer</label>
      <select id="fiscFoyer" onchange="calcFisc()">
        <option value="seul">Personne seule — abattement 4 600 €</option>
        <option value="couple">Couple (imposition commune) — 9 200 €</option>
      </select><span></span>
    </div>`;
  }

  if (t.modele_fiscal === 'per') {
    champs += `<div class="fisc-slider">
      <label>Tranche marginale d'imposition</label>
      <select id="fiscTmi" onchange="calcFisc()">
        <option value="0">0 % — non imposable</option>
        <option value="11">11 %</option>
        <option value="30" selected>30 %</option>
        <option value="41">41 %</option>
        <option value="45">45 %</option>
      </select><span></span>
    </div>`;
  }

  if (t.modele_fiscal === 'metaux') {
    const ans = anciennete(compte);
    champs += `<div class="fisc-slider">
      <label>Durée de détention</label>
      <input type="range" id="fiscAnnees" min="0" max="25" step="1"
             value="${Math.round(ans ?? 0)}" oninput="calcFisc()">
      <span id="fiscAnneesVal"></span>
    </div>`;
  }

  return `<div class="fisc-sim">${champs}</div>`;
}

export function calcFisc() {
  const compte = compteById(compteSelectionne);
  const sortie = el('fiscResultat');
  if (!compte || !sortie) return;

  const t = typeInfo(compte.type);
  const atteint = statutFiscal(compte).atteint;
  const montant = Number(el('fiscMontant')?.value || 0);
  if (el('fiscMontantVal')) el('fiscMontantVal').textContent = euro(montant);

  let gain = Number(el('fiscGain')?.value || 0);
  if (el('fiscGainVal')) el('fiscGainVal').textContent = euro(gain);
  if (['av', 'per'].includes(t.modele_fiscal)) gain = montant * ratioGains(compte);

  const annees = Number(el('fiscAnnees')?.value ?? 0);
  if (el('fiscAnneesVal')) el('fiscAnneesVal').textContent = `${annees} ans`;

  const rendu = {
    pea:    () => simPEA(montant, gain, atteint),
    flat:   () => simFlat(montant, gain),
    crypto: () => simCrypto(montant, gain),
    av:     () => simAV(montant, gain, atteint),
    per:    () => simPER(montant, gain),
    metaux: () => simMetaux(montant, gain, annees),
  }[t.modele_fiscal] || (() => simFlat(montant, gain));

  sortie.innerHTML = rendu();
}

function bloc(titre, elements, net, montant) {
  const detail = elements.map(([l, v, c]) => `
    <div class="fisc-line"><span>${l}</span><span class="${c || ''}">${euro(v)}</span></div>`).join('');
  return `<div class="fisc-block">
    <div class="fisc-block-title">${titre}</div>
    ${detail}
    <div class="fisc-line fisc-line-total">
      <span>Net encaissé</span><span class="${net >= montant ? 'pos' : ''}">${euro(net)}</span>
    </div>
  </div>`;
}

function simPEA(montant, gain, atteint) {
  if (atteint) {
    const ps = gain * PS;
    return bloc('PEA de plus de 5 ans',
      [['Impôt sur le revenu', 0, 'pos'], ['Prélèvements sociaux (17,2 %)', ps, 'neg']],
      montant - ps, montant) +
      `<div class="fisc-note pos">✅ Les retraits partiels sont possibles sans clôturer le plan.</div>`;
  }
  const ir = gain * PFU_IR, ps = gain * PS;
  return bloc('PEA de moins de 5 ans',
    [['Impôt sur le revenu (12,8 %)', ir, 'neg'], ['Prélèvements sociaux (17,2 %)', ps, 'neg']],
    montant - ir - ps, montant) +
    `<div class="fisc-note neg">⚠️ Avant 5 ans, tout retrait entraîne la clôture du plan et la taxation de l'ensemble des gains.</div>`;
}

function simFlat(montant, gain) {
  const ir = gain * PFU_IR, ps = gain * PS;
  return bloc('Flat tax (PFU 30 %)',
    [['Impôt sur le revenu (12,8 %)', ir, 'neg'], ['Prélèvements sociaux (17,2 %)', ps, 'neg']],
    montant - ir - ps, montant) +
    `<div class="fisc-note">L'option pour le barème progressif peut être plus favorable si votre TMI est de 0 % ou 11 %.</div>`;
}

function simCrypto(montant, gain) {
  if (montant < CRYPTO_SEUIL_EXONERATION) {
    return bloc('Cessions annuelles inférieures à 305 €',
      [['Impôt sur le revenu', 0, 'pos'], ['Prélèvements sociaux', 0, 'pos']],
      montant, montant) +
      `<div class="fisc-note pos">✅ Sous 305 € de cessions cumulées sur l'année, la plus-value est exonérée.</div>`;
  }
  return simFlat(montant, gain) +
    `<div class="fisc-note">Seule la conversion en euros est imposable : les échanges entre cryptoactifs ne déclenchent pas d'imposition.</div>`;
}

function simAV(montant, gain, atteint) {
  const abattement = AV_ABATTEMENT[el('fiscFoyer')?.value || 'seul'];

  const irAvant = gain * PFU_IR, psAvant = gain * PS;
  const avant = bloc('Avant 8 ans',
    [['Quote-part de gains rachetée', gain, ''],
     ['Impôt sur le revenu (12,8 %)', irAvant, 'neg'],
     ['Prélèvements sociaux (17,2 %)', psAvant, 'neg']],
    montant - irAvant - psAvant, montant);

  const abattu = Math.min(gain, abattement);
  const irApres = Math.max(0, gain - abattu) * AV_IR_REDUIT;
  const psApres = gain * PS;
  const apres = bloc('Après 8 ans',
    [['Quote-part de gains rachetée', gain, ''],
     ['Abattement appliqué', abattu, 'pos'],
     ['Impôt sur le revenu (7,5 %)', irApres, 'neg'],
     ['Prélèvements sociaux (17,2 %)', psApres, 'neg']],
    montant - irApres - psApres, montant);

  const economie = (irAvant + psAvant) - (irApres + psApres);
  const conclusion = atteint
    ? `<div class="fisc-note pos">✅ Votre contrat a dépassé 8 ans : le régime de droite s'applique.</div>`
    : `<div class="fisc-note">En attendant le cap des 8 ans, l'économie d'impôt sur ce rachat serait de
       <strong class="pos">${euro(economie)}</strong>.</div>`;

  return `<div class="fisc-compare">${avant}${apres}</div>${conclusion}`;
}

function simPER(montant, gain) {
  const tmi = Number(el('fiscTmi')?.value || 30) / 100;
  const capital = Math.max(0, montant - gain);
  const irCapital = capital * tmi;
  const impotGains = gain * PFU;

  return bloc('Sortie en capital',
    [['Quote-part de versements', capital, ''],
     [`Impôt sur les versements déduits (${(tmi * 100).toFixed(0)} %)`, irCapital, 'neg'],
     ['Quote-part de gains', gain, ''],
     ['Flat tax sur les gains (30 %)', impotGains, 'neg']],
    montant - irCapital - impotGains, montant) +
    `<div class="fisc-note">Ce calcul suppose que les versements ont été déduits du revenu imposable à l'entrée.
     Si vous y aviez renoncé, seule la quote-part de gains est imposée.</div>`;
}

function simMetaux(montant, gain, annees) {
  const forfait = montant * METAUX_FORFAIT;
  const abattement = abattementMetaux(annees);
  const pvImposable = gain * (1 - abattement);
  const regimePv = pvImposable * METAUX_PV;
  const meilleur = regimePv <= forfait ? 'pv' : 'forfait';

  const blocForfait = bloc('Taxe forfaitaire (11,5 %)',
    [['Assiette : prix de cession', montant, ''], ['Taxe forfaitaire', forfait, 'neg']],
    montant - forfait, montant);

  const blocPv = bloc(`Régime des plus-values réelles (36,2 %)`,
    [['Plus-value brute', gain, ''],
     [`Abattement pour ${annees} ans de détention (${(abattement * 100).toFixed(0)} %)`, gain * abattement, 'pos'],
     ['Plus-value imposable', pvImposable, ''],
     ['Imposition', regimePv, 'neg']],
    montant - regimePv, montant);

  return `<div class="fisc-compare">${blocForfait}${blocPv}</div>
    <div class="fisc-note ${meilleur === 'pv' ? 'pos' : ''}">
      ${meilleur === 'pv'
        ? `✅ Le régime des plus-values réelles est plus avantageux ici (${euro(forfait - regimePv)} d'économie) — il suppose de disposer des justificatifs d'achat.`
        : `La taxe forfaitaire est plus avantageuse ici (${euro(regimePv - forfait)} d'économie) et ne demande aucun justificatif d'achat.`}
    </div>`;
}

// ══════════════════════════════════════════════════════════════
// POSITIONS EN GAIN
// ══════════════════════════════════════════════════════════════
function tableauGains(positions, taux) {
  const th = 'style="padding:7px 0;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
  const td = 'style="padding:7px 0;border-bottom:1px solid var(--border)"';

  if (!positions.length) {
    return `<tbody><tr><td ${td} class="muted">
      Aucune position en gain — aucune imposition en cas de sortie aujourd'hui.
    </td></tr></tbody>`;
  }

  const lignes = positions
    .sort((a, b) => (b.pv_latent || 0) - (a.pv_latent || 0))
    .map(p => `<tr>
      <td ${td}>${esc(p.nom)}</td>
      <td ${td} style="text-align:right" class="pos">+${euro(p.pv_latent)}</td>
      <td ${td} style="text-align:right" class="neg">${euro(p.pv_latent * taux)}</td>
      <td ${td} style="text-align:right">${euro(p.pv_latent * (1 - taux))}</td>
    </tr>`).join('');

  return `<thead><tr>
      <th ${th}>Position</th>
      <th ${th} style="text-align:right">Gain latent</th>
      <th ${th} style="text-align:right">Imposition estimée</th>
      <th ${th} style="text-align:right">Gain net</th>
    </tr></thead><tbody>${lignes}</tbody>`;
}
