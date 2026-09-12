import { Store, typeInfo, comptes, compteById } from './state.js';
import { api } from './api.js';
import {
  showTab, showAccount, reload, fmt, fmtP, fmtQty, fmtDevise, fmtDate,
  cls, esc, kpiCard, badgeType, emptyState, parseNum,
} from './core.js';

let typeSelectionne = null;   // type retenu dans la modale de compte
let compteEnEdition = null;   // id du compte en cours de modification, null en création

// ══════════════════════════════════════════════════════════════
// ANCIENNETÉ / FISCALITÉ
// ══════════════════════════════════════════════════════════════
/** Ancienneté du compte en années décimales, ou null si la date est absente. */
export function anciennete(compte) {
  if (!compte?.date_ouverture) return null;
  const ouverture = new Date(compte.date_ouverture);
  if (isNaN(ouverture)) return null;
  return (Date.now() - ouverture.getTime()) / (365.25 * 24 * 3600 * 1000);
}

/** Décrit où en est le compte vis-à-vis du seuil fiscal de son enveloppe. */
export function statutFiscal(compte) {
  const t = typeInfo(compte.type);
  const ans = anciennete(compte);
  if (!t.seuil_ans) return { texte: 'Sans seuil de durée', atteint: null, ans };
  if (ans == null) return { texte: 'Date d\'ouverture non renseignée', atteint: null, ans };
  if (ans >= t.seuil_ans) {
    return { texte: `Seuil de ${t.seuil_ans} ans atteint`, atteint: true, ans };
  }
  const restant = t.seuil_ans - ans;
  const delai = restant >= 2
    ? `${Math.round(restant)} ans`
    : `${Math.max(1, Math.ceil(restant * 12))} mois`;
  return { texte: `Seuil de ${t.seuil_ans} ans dans ${delai}`, atteint: false, ans };
}

// ══════════════════════════════════════════════════════════════
// MENU LATÉRAL
// ══════════════════════════════════════════════════════════════
export function renderSidebar() {
  const liste = comptes();
  const items = liste.map(c => {
    const t = typeInfo(c.type);
    return `<div class="nav-subitem" data-tab="compte-${c.id}" onclick="showAccount(${c.id})">
      <span class="nav-dot" style="background:${t.couleur}"></span>${esc(c.nom)}
    </div>`;
  }).join('');

  document.getElementById('comptesSubmenu').innerHTML =
    (items || '<div class="nav-subitem nav-subitem-muted">Aucun compte</div>') +
    `<div class="nav-subitem nav-subitem-action" data-tab="comptes" onclick="showTab('comptes')">⚙ Gérer les comptes</div>`;
}

// ══════════════════════════════════════════════════════════════
// PAGE « MES COMPTES »
// ══════════════════════════════════════════════════════════════
export function renderComptesPage() {
  const liste = comptes();
  const el = document.getElementById('comptesList');
  if (!el) return;

  if (!liste.length) {
    el.innerHTML = emptyState(
      'Aucun compte pour l\'instant',
      'Créez votre première enveloppe pour commencer à suivre vos placements.',
      '<button class="btn primary" onclick="openAccountModal()">+ Créer un compte</button>');
    return;
  }

  el.innerHTML = `<div class="account-grid">${liste.map(carteCompte).join('')}</div>`;
}

function carteCompte(c) {
  const t = typeInfo(c.type);
  const statut = statutFiscal(c);
  const sousTitre = [c.etablissement, c.date_ouverture ? `ouvert le ${fmtDate(c.date_ouverture)}` : '']
    .filter(Boolean).map(esc).join(' · ');

  return `<div class="account-card" style="border-top:3px solid ${t.couleur}">
    <div class="account-card-head">
      <div>
        <div class="account-card-title">${esc(t.icone)} ${esc(c.nom)}</div>
        <div class="account-card-sub">${sousTitre || esc(t.nom_complet || t.label)}</div>
      </div>
      ${badgeType(c.type)}
    </div>
    <div class="account-card-value">${fmt(c.valorisation)}</div>
    <div class="account-card-meta">
      <span class="${cls(c.pv_latent)}">${fmt(c.pv_latent)} (${fmtP(c.pv_pct)})</span>
      <span>${c.nb_positions} position${c.nb_positions > 1 ? 's' : ''}</span>
    </div>
    ${statut.ans != null ? `<div class="account-card-note ${statut.atteint ? 'pos' : ''}">${esc(statut.texte)}</div>` : ''}
    ${c.note ? `<div class="account-card-note">${esc(c.note)}</div>` : ''}
    <div class="account-card-actions">
      <button class="btn" onclick="showAccount(${c.id})">Ouvrir</button>
      <button class="btn" onclick="openAccountModal(${c.id})">✏️ Modifier</button>
    </div>
  </div>`;
}

// ══════════════════════════════════════════════════════════════
// PAGE D'UN COMPTE
// ══════════════════════════════════════════════════════════════
export function renderAccountPage() {
  const compte = compteById(Store.currentAccountId);
  if (!compte) { showTab('comptes'); return; }

  const t = typeInfo(compte.type);
  const positions = compte.positions || [];
  const statut = statutFiscal(compte);

  document.getElementById('compteTitre').textContent = `${t.icone} ${compte.nom}`;
  document.getElementById('compteSousTitre').textContent =
    [t.nom_complet || t.label, compte.etablissement,
     compte.date_ouverture ? `ouvert le ${fmtDate(compte.date_ouverture)}` : ''].filter(Boolean).join(' · ');

  document.getElementById('compteCards').innerHTML =
    kpiCard('Valorisation', fmt(compte.valorisation)) +
    kpiCard('Investi', fmt(compte.investi)) +
    kpiCard('+/- Latent', fmt(compte.pv_latent), fmtP(compte.pv_pct), cls(compte.pv_pct)) +
    kpiCard('Positions', String(positions.length), t.unite, 'neu') +
    (statut.ans != null
      ? kpiCard('Ancienneté', `${statut.ans.toFixed(1)} ans`, statut.texte, statut.atteint ? 'pos' : 'neu')
      : '');

  const table = document.getElementById('compteTable');
  const entetes = `<thead><tr>
      <th>Valeur</th><th>Ticker</th><th>Qté (${esc(t.unite)})</th>
      <th>Cours</th><th>PRU</th><th>Valorisation</th>
      <th>+/- Latent</th><th>+/- %</th><th>Var. J</th><th>Actions</th>
    </tr></thead>`;

  if (!positions.length) {
    table.innerHTML = entetes + `<tbody><tr><td colspan="10" class="table-empty">
      Aucune position — cliquez sur « + Position » pour en ajouter une.
    </td></tr></tbody>`;
    return;
  }

  const lignes = positions.map(p => {
    const devise = p.devise || 'EUR';
    const fx = devise !== 'EUR' && p.taux_change
      ? `<span class="fx-hint">×${p.taux_change.toFixed(4)}</span>` : '';
    return `<tr>
      <td>${esc(p.nom)}${p.isin ? `<div class="cell-sub">${esc(p.isin)}</div>` : ''}</td>
      <td class="mono">${esc(p.ticker) || '<span class="muted">manuel</span>'}</td>
      <td>${fmtQty(p.quantite, t.decimales)}</td>
      <td>${fmtDevise(p.cours, devise)}${fx}</td>
      <td>${fmtDevise(p.pru, devise)}</td>
      <td>${fmt(p.valorisation)}</td>
      <td class="${cls(p.pv_latent)}">${fmt(p.pv_latent)}</td>
      <td class="${cls(p.pv_pct)}">${fmtP(p.pv_pct)}</td>
      <td class="${cls(p.variation)}">${p.variation != null ? fmtP(p.variation) : '—'}</td>
      <td class="actions">
        <button class="btn btn-mini" onclick="openPositionModal(${p.id})">✏️</button>
        <button class="btn btn-mini" onclick="delPos(${p.id})">🗑</button>
      </td>
    </tr>`;
  }).join('');

  const totalPv = positions.reduce((s, p) => s + (p.pv_latent || 0), 0);
  const pied = `<tr class="tfoot">
    <td colspan="5">Total ${esc(compte.nom)}</td>
    <td>${fmt(compte.valorisation)}</td>
    <td class="${cls(totalPv)}">${fmt(totalPv)}</td>
    <td class="${cls(compte.pv_pct)}">${fmtP(compte.pv_pct)}</td>
    <td></td><td></td>
  </tr>`;

  table.innerHTML = entetes + `<tbody>${lignes}</tbody><tfoot>${pied}</tfoot>`;
}

// ══════════════════════════════════════════════════════════════
// MODALE DE COMPTE
// ══════════════════════════════════════════════════════════════
export function openAccountModal(id = null) {
  compteEnEdition = id;
  const compte = id ? compteById(id) : null;

  document.getElementById('accountModalTitle').textContent = compte ? 'Modifier le compte' : 'Nouveau compte';
  document.getElementById('btnDeleteAccount').style.display = compte ? '' : 'none';
  document.getElementById('accountError').textContent = '';

  typeSelectionne = compte ? compte.type : (Store.TYPES_LIST[0]?.id || 'pea');
  renderTypePicker();

  document.getElementById('aNom').value = compte?.nom || '';
  document.getElementById('aEtablissement').value = compte?.etablissement || '';
  document.getElementById('aDateOuverture').value = compte?.date_ouverture || '';
  document.getElementById('aCible').value = compte?.cible_pct ? String(compte.cible_pct) : '';
  document.getElementById('aFrais').value = compte?.frais_pct ? String(compte.frais_pct) : '';
  document.getElementById('aNote').value = compte?.note || '';

  document.getElementById('accountModal').classList.add('open');
  if (!compte) appliquerExemples();
}

export function editCurrentAccount() {
  if (Store.currentAccountId) openAccountModal(Store.currentAccountId);
}

export function closeAccountModal() {
  document.getElementById('accountModal').classList.remove('open');
}

function renderTypePicker() {
  document.getElementById('accountTypePicker').innerHTML = Store.TYPES_LIST.map(t => `
    <button type="button" class="type-chip ${t.id === typeSelectionne ? 'active' : ''}"
            style="--chip:${t.couleur}" onclick="selectAccountType('${t.id}')">
      <span class="type-chip-icon">${esc(t.icone)}</span>
      <span>${esc(t.label)}</span>
    </button>`).join('');

  const t = typeInfo(typeSelectionne);
  document.getElementById('accountTypeHelp').textContent = t.resume_fiscal || '';

  const indice = document.getElementById('accountDateHint');
  indice.innerHTML = t.seuil_ans
    ? `📅 La date d'ouverture sert à savoir si le seuil des <strong>${t.seuil_ans} ans</strong> est atteint dans l'onglet Fiscalité.`
    : `📅 La date d'ouverture est facultative pour ce type d'enveloppe : aucun avantage fiscal n'y est lié à la durée de détention.`;
}

export function selectAccountType(id) {
  typeSelectionne = id;
  renderTypePicker();
  if (!compteEnEdition) appliquerExemples();
}

/** Pré-remplit nom et établissement avec les exemples du type choisi (création seulement). */
function appliquerExemples() {
  const t = typeInfo(typeSelectionne);
  const nom = document.getElementById('aNom');
  const etab = document.getElementById('aEtablissement');
  if (!nom.value || nom.dataset.auto === '1') {
    nom.value = t.exemple_nom || t.label;
    nom.dataset.auto = '1';
  }
  etab.placeholder = t.exemple_etablissement || '';
  nom.oninput = () => { nom.dataset.auto = '0'; };
}

export async function saveAccount() {
  const erreur = document.getElementById('accountError');
  erreur.textContent = '';

  const payload = {
    nom: document.getElementById('aNom').value.trim(),
    type: typeSelectionne,
    etablissement: document.getElementById('aEtablissement').value.trim(),
    date_ouverture: document.getElementById('aDateOuverture').value,
    cible_pct: parseNum(document.getElementById('aCible').value),
    frais_pct: parseNum(document.getElementById('aFrais').value),
    note: document.getElementById('aNote').value.trim(),
  };

  try {
    if (compteEnEdition) {
      await api.updateAccount(compteEnEdition, payload);
    } else {
      const cree = await api.createAccount(payload);
      Store.currentAccountId = cree.id;
    }
    closeAccountModal();
    await reload();
    if (Store.currentAccountId) showAccount(Store.currentAccountId);
  } catch (e) {
    erreur.textContent = e.message;
  }
}

export async function deleteCurrentAccount() {
  const compte = compteById(compteEnEdition);
  if (!compte) return;
  const nb = compte.nb_positions;
  const message = nb
    ? `Supprimer « ${compte.nom} » et ses ${nb} position${nb > 1 ? 's' : ''} ?\nLes dividendes rattachés seront également supprimés.`
    : `Supprimer « ${compte.nom} » ?`;
  if (!confirm(message)) return;

  try {
    await api.deleteAccount(compte.id);
    closeAccountModal();
    if (Store.currentAccountId === compte.id) Store.currentAccountId = null;
    await reload();
    showTab('comptes');
  } catch (e) {
    document.getElementById('accountError').textContent = e.message;
  }
}

// ══════════════════════════════════════════════════════════════
// SUPPRESSION D'UNE POSITION (depuis le tableau d'un compte)
// ══════════════════════════════════════════════════════════════
export async function delPos(positionId) {
  if (!confirm('Supprimer cette position ?')) return;
  try {
    await api.deletePosition(positionId);
    await reload();
  } catch (e) {
    alert('Suppression impossible : ' + e.message);
  }
}
