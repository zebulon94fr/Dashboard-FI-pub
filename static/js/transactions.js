// Journal des mouvements : saisie, consultation et plus-values réalisées.
// C'est lui qui alimente le PMP des positions et les flux datés du TWR/TRI ;
// les champs quantité, PRU et prix de revient d'une position en découlent.
import { Store, typeInfo, comptes, compteById } from './state.js';
import { api } from './api.js';
import { reload, fmt, cls, esc, kpiCard, badgeType, fmtDate, parseNum } from './core.js';

let mouvementEnEdition = null;
let dernierChargement = { transactions: [], plus_values: [] };

const el = id => document.getElementById(id);

const typesTx = () => Store.TX_TYPES || [];
const typeTx = id => typesTx().find(t => t.id === id) || { label: id, sens: 1, ligne: false };

function optionsComptes(vide = null) {
  return (vide ? `<option value="">${esc(vide)}</option>` : '') +
    comptes().map(c => `<option value="${c.id}">${esc(c.nom)}</option>`).join('');
}

// ══════════════════════════════════════════════════════════════
// MODALE
// ══════════════════════════════════════════════════════════════
export function openTxModal(id = null) {
  if (!comptes().length) {
    alert('Créez d\'abord un compte pour y enregistrer des mouvements.');
    return;
  }

  mouvementEnEdition = id;
  el('txModalTitle').textContent = id ? 'Modifier le mouvement' : 'Enregistrer un mouvement';
  el('txError').textContent = '';
  el('txCompte').innerHTML = optionsComptes();
  el('txType').innerHTML = typesTx()
    .map(t => `<option value="${t.id}">${esc(t.icone)} ${esc(t.label)}</option>`).join('');

  if (!id) {
    el('txDate').value = new Date().toISOString().slice(0, 10);
    el('txCompte').value = String(Store.currentAccountId || comptes()[0].id);
    el('txType').value = 'achat';
    ['txQuantite', 'txPrix', 'txTaux', 'txFrais', 'txMontant', 'txNote']
      .forEach(champ => { el(champ).value = ''; });
  }

  onTxAccountChange();
  el('txModal').classList.add('open');
}

export function closeTxModal() { el('txModal').classList.remove('open'); }

/** Recharge la liste des positions du compte choisi. */
export function onTxAccountChange() {
  const compte = compteById(el('txCompte').value);
  const positions = compte?.positions || [];
  el('txPosition').innerHTML = positions.length
    ? positions.map(p => `<option value="${p.id}">${esc(p.nom)}</option>`).join('')
    : '<option value="">— aucune position dans ce compte —</option>';

  const t = compte ? typeInfo(compte.type) : null;
  el('txDevise').innerHTML = (Store.DEVISES || ['EUR'])
    .map(d => `<option value="${d}">${d}</option>`).join('');
  if (t?.devise_defaut) el('txDevise').value = t.devise_defaut;

  onTxTypeChange();
}

/** Un achat ou une vente porte sur une ligne ; le reste porte sur l'enveloppe. */
export function onTxTypeChange() {
  const surLigne = typeTx(el('txType').value).ligne;
  el('txChampsLigne').hidden = !surLigne;
  el('txChampsMontant').hidden = surLigne;

  const compte = compteById(el('txCompte').value);
  const positions = compte?.positions || [];
  el('txHint').textContent = surLigne
    ? (positions.length
        ? 'Quantité et prix unitaire dans la devise de la ligne. Le prix de revient en euros est figé à cette date.'
        : 'Créez d\'abord une position dans ce compte : un achat doit désigner la ligne qu\'il alimente.')
    : 'Mouvement d\'espèces sur l\'enveloppe entière : il date un flux sans toucher au prix de revient d\'une ligne.';

  onTxDeviseChange();
}

/** Le taux de change n'a de sens que hors zone euro. */
export function onTxDeviseChange() {
  const horsEuro = el('txDevise').value !== 'EUR';
  el('txTauxGroup').hidden = !horsEuro;
}

export async function saveTransaction() {
  const erreur = el('txError');
  erreur.textContent = '';

  const type = el('txType').value;
  const payload = {
    date: el('txDate').value,
    account_id: Number(el('txCompte').value),
    type,
    note: el('txNote').value.trim(),
    frais: parseNum(el('txFrais').value),
  };

  if (typeTx(type).ligne) {
    if (!el('txPosition').value) {
      erreur.textContent = 'Choisissez la position concernée par ce mouvement.';
      return;
    }
    Object.assign(payload, {
      position_id: Number(el('txPosition').value),
      quantite: parseNum(el('txQuantite').value),
      prix: parseNum(el('txPrix').value),
      devise: el('txDevise').value,
      taux_change: el('txTaux').value.trim() ? parseNum(el('txTaux').value) : null,
    });
  } else {
    payload.montant = parseNum(el('txMontant').value);
  }

  const bouton = el('txSaveBtn');
  bouton.disabled = true;
  try {
    if (mouvementEnEdition) await api.updateTransaction(mouvementEnEdition, payload);
    else await api.createTransaction(payload);
    closeTxModal();
    // Le journal réécrit quantité et PRU : il faut recharger le portefeuille.
    await reload();
    loadTransactions();
  } catch (e) {
    erreur.textContent = e.message;
  }
  bouton.disabled = false;
}

export function editTransaction(id) {
  const mouvement = dernierChargement.transactions.find(t => t.id === id);
  if (!mouvement) return;

  openTxModal(id);
  el('txDate').value = mouvement.date;
  el('txCompte').value = String(mouvement.account_id);
  onTxAccountChange();
  el('txType').value = mouvement.type;
  onTxTypeChange();

  if (typeTx(mouvement.type).ligne) {
    if (mouvement.position_id) el('txPosition').value = String(mouvement.position_id);
    el('txQuantite').value = mouvement.quantite;
    el('txPrix').value = mouvement.prix;
    el('txDevise').value = mouvement.devise;
    el('txTaux').value = mouvement.devise === 'EUR' ? '' : mouvement.taux_change;
    onTxDeviseChange();
  } else {
    el('txMontant').value = mouvement.montant_eur;
  }
  el('txFrais').value = mouvement.frais || '';
  el('txNote').value = mouvement.note || '';
}

export async function deleteTransaction(id) {
  if (!confirm('Supprimer ce mouvement ? La quantité et le PRU de la position seront recalculés.')) return;
  try {
    await api.deleteTransaction(id);
    await reload();
    loadTransactions();
  } catch (e) {
    alert('Suppression impossible : ' + e.message);
  }
}

// ══════════════════════════════════════════════════════════════
// AFFICHAGE
// ══════════════════════════════════════════════════════════════
export async function loadTransactions() {
  const filtreCompte = el('txFilterCompte');
  const compteChoisi = filtreCompte.value;
  filtreCompte.innerHTML = optionsComptes('Tous les comptes');
  filtreCompte.value = compteChoisi;

  let d;
  try {
    d = await api.getTransactions({
      account_id: compteChoisi,
      type: el('txFilterType').value,
      annee: el('txFilterAnnee').value,
    });
  } catch (e) {
    el('txCards').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }
  dernierChargement = d;

  const s = d.stats || {};
  const entrees = s.total_entrees || 0;
  const sorties = s.total_sorties || 0;
  const realise = (d.plus_values || []).reduce((somme, l) => somme + l.pv_realisee, 0);

  el('txCards').innerHTML =
    kpiCard('Capital engagé', fmt(entrees), 'achats et versements', 'neu') +
    kpiCard('Capital retiré', fmt(sorties), 'ventes, retraits et frais', 'neu') +
    kpiCard('Flux net', fmt(entrees - sorties), 'ce qui est encore investi', 'neu') +
    kpiCard('Plus-values réalisées', fmt(realise),
      `${(d.plus_values || []).length} ligne${(d.plus_values || []).length > 1 ? 's' : ''} vendue${(d.plus_values || []).length > 1 ? 's' : ''}`,
      cls(realise)) +
    kpiCard('Mouvements', `${s.nb || 0}`, s.premier ? `depuis le ${fmtDate(s.premier)}` : '', 'neu');

  renderPlusValues(d.plus_values || []);
  renderJournal(d.transactions || []);
  remplirAnnees(d.transactions || []);
}

function remplirAnnees(mouvements) {
  const selecteur = el('txFilterAnnee');
  const choisie = selecteur.value;
  const annees = [...new Set(mouvements.map(t => t.date.slice(0, 4)))].sort().reverse();
  selecteur.innerHTML = '<option value="">Toutes années</option>' +
    annees.map(a => `<option value="${a}">${a}</option>`).join('');
  selecteur.value = choisie;
}

const TH = 'style="padding:6px 10px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
const TD = 'style="padding:6px 10px;border-bottom:1px solid var(--border)"';

function renderPlusValues(lignes) {
  if (!lignes.length) {
    el('txPlusValues').innerHTML =
      '<div class="table-empty">Aucune vente enregistrée — la plus-value réalisée apparaîtra ici, '
      + 'séparée de la plus-value latente.</div>';
    return;
  }

  el('txPlusValues').innerHTML =
    `<thead><tr>
      <th ${TH}>Position</th><th ${TH}>Compte</th>
      <th ${TH} style="text-align:right">Plus-value réalisée</th>
      <th ${TH} style="text-align:right">Ventes</th>
    </tr></thead><tbody>` +
    lignes.map(l => `<tr>
      <td ${TD}>${esc(l.nom)}</td>
      <td ${TD}>${badgeType(l.compte_type)} ${esc(l.compte || '')}</td>
      <td ${TD} style="text-align:right" class="${cls(l.pv_realisee)}">${fmt(l.pv_realisee)}</td>
      <td ${TD} style="text-align:right">${l.nb_ventes}</td>
    </tr>`).join('') + '</tbody>';
}

function renderJournal(mouvements) {
  if (!mouvements.length) {
    el('txTable').innerHTML =
      `<tbody><tr><td class="table-empty">Aucun mouvement enregistré — cliquez sur « + Mouvement ».
        Sans journal, le dashboard ne peut calculer ni TWR, ni TRI, ni plus-value réalisée.</td></tr></tbody>`;
    return;
  }

  const lignes = mouvements.map(t => {
    const info = typeTx(t.type);
    const signe = info.sens > 0 ? '+' : '−';
    const detail = info.ligne
      ? `${t.quantite} × ${t.prix} ${t.devise === 'EUR' ? '€' : esc(t.devise)}`
      : '<span class="muted">—</span>';
    const fx = (t.devise && t.devise !== 'EUR')
      ? `<span class="fx-hint">× ${Number(t.taux_change).toFixed(4)}</span>` : '';

    return `<tr>
      <td ${TD}>${esc(fmtDate(t.date))}</td>
      <td ${TD}><span class="tag tx-${esc(t.type)}">${esc(info.icone)} ${esc(info.label)}</span></td>
      <td ${TD}>${badgeType(t.compte_type)} ${esc(t.compte || '')}</td>
      <td ${TD}>${t.nom ? esc(t.nom) : '<span class="muted">—</span>'}</td>
      <td ${TD}>${detail}${fx}</td>
      <td ${TD} style="text-align:right">${t.frais ? fmt(t.frais) : '<span class="muted">—</span>'}</td>
      <td ${TD} style="text-align:right" class="${t.type === 'frais' ? 'neg' : 'neu'}">${signe} ${fmt(t.montant_eur)}</td>
      <td ${TD} class="muted" style="font-size:12px">${esc(t.note || '')}</td>
      <td ${TD} class="actions">
        <button class="btn btn-mini" onclick="editTransaction(${t.id})" title="Modifier">✏️</button>
        <button class="btn btn-mini" onclick="deleteTransaction(${t.id})" title="Supprimer">🗑</button>
      </td>
    </tr>`;
  }).join('');

  el('txTable').innerHTML =
    `<thead><tr>
      <th ${TH}>Date</th><th ${TH}>Type</th><th ${TH}>Compte</th><th ${TH}>Ligne</th>
      <th ${TH}>Détail</th><th ${TH} style="text-align:right">Frais</th>
      <th ${TH} style="text-align:right">Montant</th><th ${TH}>Note</th><th ${TH}>Actions</th>
    </tr></thead><tbody>${lignes}</tbody>`;
}
