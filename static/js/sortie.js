// Ce qui se décide avant de retirer ou de déclarer : d'où sortir une somme au
// moindre coût, ce qu'il reste de franchise cette année, et quelles cessions
// reporter sur la 2074 ou la 2086.
//
// L'onglet Fiscalité simule déjà un retrait enveloppe par enveloppe. Ces trois
// panneaux répondent aux questions qu'une enveloppe seule ne peut pas trancher,
// parce qu'elles se jouent sur l'ensemble du patrimoine ou sur l'année entière.
import { api } from './api.js';
import { fmt, esc, parseNum, badgeType } from './core.js';

const el = id => document.getElementById(id);

const TH = 'style="padding:5px 8px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
const TD = 'style="padding:5px 8px;border-bottom:1px solid var(--border)"';

/** Taux affiché sans signe ni décimale superflue : « 6,9 % ». */
const taux = v => (v * 100).toFixed(1).replace('.', ',') + ' %';

let dernierPlan = null;
let minuterie = null;

export function loadSortie() {
  remplirAnnees();
  planifierRetrait();
  chargerAbattements();
  chargerCessions();
}

const couple = () => Boolean(el('sortieCouple')?.value);

// ══════════════════════════════════════════════════════════════
// PLAN DE RETRAIT
// ══════════════════════════════════════════════════════════════
export function planifierRetrait() {
  // La saisie se fait au clavier : on attend une pause plutôt que d'interroger
  // le serveur à chaque chiffre tapé.
  clearTimeout(minuterie);
  minuterie = setTimeout(executerPlan, 350);
}

async function executerPlan() {
  const zone = el('sortiePlan');
  if (!zone) return;
  const besoin = parseNum(el('sortieBesoin').value);

  if (!besoin || besoin <= 0) {
    zone.innerHTML = '<div class="chart-hint">Indiquez la somme dont vous avez besoin : '
      + 'le dashboard classe vos enveloppes par coût fiscal réel du retrait, '
      + 'et répartit le montant en commençant par les moins taxées.</div>';
    return;
  }

  let plan;
  try {
    plan = await api.getPlanRetrait({ besoin, couple: couple() });
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }
  dernierPlan = plan;

  if (!plan.etapes.length) {
    zone.innerHTML = '<div class="table-empty">Aucune enveloppe disponible pour ce retrait.</div>';
    return;
  }

  const lignes = plan.etapes.map(e => `<tr>
    <td ${TD}>${badgeType(e.type)} ${esc(e.compte)}</td>
    <td ${TD} style="text-align:right">${fmt(e.retire)}</td>
    <td ${TD} style="text-align:right" class="${e.impot ? 'neg' : 'pos'}">${fmt(e.impot)}</td>
    <td ${TD} style="text-align:right">${e.retire ? taux(e.impot / e.retire) : '—'}</td>
    <td ${TD} style="text-align:right;font-weight:600">${fmt(e.net)}</td>
  </tr>`).join('');

  const notes = [...new Set(plan.etapes.flatMap(e => e.notes))];

  zone.innerHTML = `
    <table style="width:100%;font-size:13px;border-collapse:collapse">
      <thead><tr>
        <th ${TH}>Enveloppe</th>
        <th ${TH} style="text-align:right">Retiré</th>
        <th ${TH} style="text-align:right">Impôt</th>
        <th ${TH} style="text-align:right">Taux</th>
        <th ${TH} style="text-align:right">Net</th>
      </tr></thead>
      <tbody>${lignes}</tbody>
      <tfoot><tr>
        <td ${TD} style="font-weight:600">Total</td>
        <td ${TD} style="text-align:right;font-weight:600">${fmt(plan.couvert)}</td>
        <td ${TD} style="text-align:right;font-weight:600" class="${plan.impot_total ? 'neg' : 'pos'}">${fmt(plan.impot_total)}</td>
        <td ${TD} style="text-align:right;font-weight:600">${taux(plan.taux_moyen)}</td>
        <td ${TD} style="text-align:right;font-weight:600">${fmt(plan.net_total)}</td>
      </tr></tfoot>
    </table>
    ${plan.manquant > 0
      ? `<div class="hint-box" style="border-color:var(--red);margin-top:10px">
           Il manque ${fmt(plan.manquant)} : vos enveloppes disponibles ne couvrent pas ce besoin.
         </div>`
      : ''}
    ${plan.ecartees.length
      ? `<div class="chart-hint" style="margin-top:10px">Écartées : ${plan.ecartees
          .map(x => `<strong>${esc(x.compte)}</strong> (${esc(x.motif)})`).join(', ')}.</div>`
      : ''}
    ${notes.length
      ? `<div class="chart-hint" style="margin-top:8px">${notes.map(esc).join('<br>')}</div>`
      : ''}
    <div class="chart-hint" style="margin-top:8px">
      Estimations : elles ignorent votre tranche marginale et votre situation personnelle.
      Elles servent à comparer deux guichets, pas à remplir une déclaration.
    </div>`;
}

// ══════════════════════════════════════════════════════════════
// FRANCHISES DE L'ANNÉE
// ══════════════════════════════════════════════════════════════
async function chargerAbattements() {
  const zone = el('sortieAbattements');
  if (!zone) return;
  let d;
  try {
    d = await api.getAbattements({ couple: couple() });
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  const av = d.assurance_vie;
  const crypto = d.crypto;
  const jauge = (part, couleur) =>
    `<span class="cal-bar"><span style="width:${Math.min(100, part * 100).toFixed(1)}%;background:${couleur}"></span></span>`;

  const partAv = av.plafond ? Math.min(1, av.gains_rachetes / av.plafond) : 0;
  const partCrypto = crypto.seuil ? Math.min(1, crypto.cessions / crypto.seuil) : 0;

  zone.innerHTML = `
    <div class="cal-row">
      <span class="cal-name">🛡 Assurance vie — abattement annuel</span>
      <span class="cal-when ${av.restant > 0 ? 'pos' : 'neg'}">${fmt(av.restant)}</span>
      <span class="cal-sub">${fmt(av.gains_rachetes)} de gains rachetés sur ${fmt(av.plafond)}
        ${av.gains_rachetes > 0 ? '— estimés au prorata des gains du jour' : ''}</span>
      ${jauge(partAv, partAv >= 1 ? 'var(--red)' : 'var(--green)')}
    </div>
    <div class="cal-row">
      <span class="cal-name">₿ Cryptoactifs — seuil de cession</span>
      <span class="cal-when ${crypto.depasse ? 'neg' : 'pos'}">${crypto.depasse ? '⚠ dépassé' : fmt(crypto.restant)}</span>
      <span class="cal-sub">${fmt(crypto.cessions)} cédés sur ${fmt(crypto.seuil)} —
        ${crypto.depasse
          ? 'la plus-value de l\'année est imposable'
          : 'en deçà, la plus-value reste exonérée'}</span>
      ${jauge(partCrypto, crypto.depasse ? 'var(--red)' : 'var(--green)')}
    </div>
    <div class="chart-hint" style="margin-top:8px">
      Deux franchises qui se jugent sur l'année civile entière, et non opération par opération.
    </div>`;
}

// ══════════════════════════════════════════════════════════════
// CESSIONS À DÉCLARER
// ══════════════════════════════════════════════════════════════
function remplirAnnees() {
  const selecteur = el('sortieAnnee');
  if (!selecteur || selecteur.options.length) return;
  const courante = new Date().getFullYear();
  selecteur.innerHTML = Array.from({ length: 6 }, (_, i) => courante - i)
    .map(a => `<option value="${a}">${a}</option>`).join('');
}

export async function chargerCessions() {
  const zone = el('sortieCessions');
  if (!zone) return;
  let d;
  try {
    d = await api.getCessions(el('sortieAnnee').value);
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  if (!d.formulaires.length) {
    zone.innerHTML = `<div class="table-empty">Aucune cession enregistrée en ${d.annee}.
      Les plus-values réalisées se reconstituent depuis le journal des mouvements.</div>`;
    return;
  }

  zone.innerHTML = d.formulaires.map(f => `
    <div class="cal-row">
      <span class="cal-name">📄 ${esc(f.code)} — ${esc(f.libelle)}</span>
      <span class="cal-when ${f.total_plus_value >= 0 ? 'pos' : 'neg'}">${fmt(f.total_plus_value)}</span>
      <span class="cal-sub">${f.lignes.length} cession(s), ${fmt(f.total_cession)} cédés
        ${f.incompletes ? `— <span class="neg">${f.incompletes} sans prix de revient connu</span>` : ''}</span>
    </div>`).join('')
    + `<div class="chart-hint" style="margin-top:8px">
         Plus-values calculées au prix moyen pondéré depuis le journal. Une cession dont
         l'achat précède le journal est signalée « à compléter » plutôt que chiffrée à tort.
       </div>`;
}


export function exporterCessions() {
  window.open(api.exportCessionsUrl(el('sortieAnnee').value), '_blank');
}

export function planDeRetraitCourant() { return dernierPlan; }
