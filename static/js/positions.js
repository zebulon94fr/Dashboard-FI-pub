import { Store, typeInfo, comptes, compteById, toutesPositions } from './state.js';
import { api } from './api.js';
import { reload, esc, parseNum, showAccount } from './core.js';

let positionEnEdition = null;   // id de la position modifiée, null en création

// Miroir de catalog.CLASSE_PAR_DEFAUT, pour proposer une classe sans aller-retour serveur.
const CLASSE_PAR_ENVELOPPE = {
  pea: 'actions', cto: 'actions', per: 'actions',
  av: 'obligations', metaux: 'or', crypto: 'crypto',
};

export function positionById(id) {
  for (const compte of comptes()) {
    const position = (compte.positions || []).find(p => p.id === Number(id));
    if (position) return { position, compte };
  }
  return null;
}

const el = id => document.getElementById(id);

/** Valeurs déjà saisies pour un champ libre — proposées en autocomplétion. */
function valeursConnues(champ) {
  return [...new Set(toutesPositions().map(p => p[champ]).filter(Boolean))].sort();
}

function remplirDatalist(id, valeurs) {
  el(id).innerHTML = valeurs.map(v => `<option value="${esc(v)}">`).join('');
}

export function openPositionModal(positionId = null) {
  if (!comptes().length) {
    alert('Créez d\'abord un compte : c\'est lui qui porte vos positions.');
    return;
  }

  positionEnEdition = positionId;
  const trouvee = positionId ? positionById(positionId) : null;
  const position = trouvee?.position;

  el('modalTitle').textContent = position ? 'Modifier la position' : 'Ajouter une position';
  el('positionError').textContent = '';

  // Comptes disponibles
  el('fCompte').innerHTML = comptes()
    .map(c => `<option value="${c.id}">${esc(c.nom)} — ${esc(typeInfo(c.type).label)}</option>`).join('');
  el('fCompte').value = String(
    trouvee?.compte.id || Store.currentAccountId || comptes()[0].id);

  // Devises
  el('fDevise').innerHTML = Store.DEVISES
    .map(d => `<option value="${d}">${d}</option>`).join('');

  el('fNom').value     = position?.nom || '';
  el('fTicker').value  = position?.ticker || '';
  el('fIsin').value    = position?.isin || '';
  el('fQty').value     = position?.quantite ?? '';
  el('fPru').value     = position?.pru ?? '';
  el('fCours').value   = position?.cours ?? '';
  el('fSecteur').value = position?.secteur || '';
  el('fZone').value    = position?.zone || '';
  el('fTaux').value    = position?.devise && position.devise !== 'EUR' ? position.taux_change : '';
  el('fGroupe').value  = position?.groupe || '';

  el('fClasse').innerHTML = (Store.CLASSES || [])
    .map(c => `<option value="${c.id}">${esc(c.label)}</option>`).join('');
  remplirDatalist('fGroupeList', valeursConnues('groupe'));

  remplirDatalist('fSecteurList', valeursConnues('secteur'));
  remplirDatalist('fZoneList', valeursConnues('zone'));
  if (position?.classe) el('fClasse').value = position.classe;

  // L'achat initial ne concerne que la création : sur une ligne existante, les
  // opérations passent par le journal (onglet Mouvements).
  el('fAchatRow').hidden = Boolean(positionEnEdition);
  el('fAvecAchat').checked = !positionEnEdition;
  el('fDateAchat').value = new Date().toISOString().slice(0, 10);
  onPositionAchatChange();

  onPositionAccountChange(position?.devise);
  el('posModal').classList.add('open');
}

/** Adapte devise par défaut, suggestions et libellés au type du compte choisi. */
export function onPositionAccountChange(deviseForcee = null) {
  const compte = compteById(el('fCompte').value);
  const t = typeInfo(compte?.type);

  el('fDevise').value = deviseForcee || t.devise_defaut || 'EUR';

  const suggestions = t.suggestions || [];
  remplirDatalist('fTickerList', suggestions.map(s => s.ticker));
  remplirDatalist('fNomList', suggestions.length
    ? suggestions.map(s => s.nom)
    : valeursConnues('nom'));

  el('fQtyLabel').textContent = `Quantité (${t.unite})`;
  // À la création, la classe d'actifs suit le type d'enveloppe : un point de
  // départ raisonnable, que l'on reste libre de corriger.
  if (!positionEnEdition && el('fClasse').options.length) {
    el('fClasse').value = CLASSE_PAR_ENVELOPPE[compte?.type] || 'autre';
  }
  onPositionDeviseChange();
}

export function onPositionAchatChange() {
  el('fDateAchatGroup').hidden = !el('fAvecAchat').checked;
}

export function onPositionDeviseChange() {
  const devise = el('fDevise').value || 'EUR';
  el('fPruLabel').textContent   = `PRU (${devise})`;
  el('fCoursLabel').textContent = `Cours actuel (${devise})`;
  // Hors zone euro, un taux est indispensable : sans lui la position serait
  // valorisée comme si la devise était l'euro.
  el('fTauxRow').hidden = devise === 'EUR';
}

export function closeModal() { el('posModal').classList.remove('open'); }

export async function savePosition() {
  const erreur = el('positionError');
  erreur.textContent = '';

  const accountId = Number(el('fCompte').value);
  const payload = {
    nom: el('fNom').value.trim(),
    ticker: el('fTicker').value.trim().toUpperCase(),
    isin: el('fIsin').value.trim().toUpperCase(),
    secteur: el('fSecteur').value.trim(),
    zone: el('fZone').value.trim(),
    quantite: parseNum(el('fQty').value),
    pru: parseNum(el('fPru').value),
    cours: parseNum(el('fCours').value),
    devise: el('fDevise').value,
    classe: el('fClasse').value,
    groupe: el('fGroupe').value.trim(),
    taux_change: el('fTaux').value.trim() ? parseNum(el('fTaux').value) : null,
  };

  // Créer une ligne avec une quantité et un PRU, c'est décrire un achat :
  // le serveur l'inscrit au journal si une date est fournie.
  if (!positionEnEdition && el('fAvecAchat').checked) {
    payload.date_achat = el('fDateAchat').value;
  }

  if (!payload.nom) { erreur.textContent = 'Le nom de la position est obligatoire.'; return; }

  try {
    if (positionEnEdition) {
      await api.updatePosition(positionEnEdition, { ...payload, account_id: accountId });
    } else {
      await api.createPosition(accountId, payload);
    }
    closeModal();
    Store.currentAccountId = accountId;
    await reload();
    showAccount(accountId);
  } catch (e) {
    erreur.textContent = e.message;
  }
}
