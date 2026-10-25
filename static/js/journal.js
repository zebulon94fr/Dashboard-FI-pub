// Ce qui nourrit le journal des mouvements, autrement qu'à la main :
// reconstitution des prix de revient, versements programmés, import d'un
// relevé de courtier. Trois chemins vers la même table `transactions`.
import { Store, comptes } from './state.js';
import { api } from './api.js';
import { reload, fmt, esc, fmtDate, fmtDevise, fmtQty, parseNum, badgeType } from './core.js';
import { loadTransactions } from './transactions.js';

const el = id => document.getElementById(id);

const TH = 'style="padding:6px 10px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
const TD = 'style="padding:6px 10px;border-bottom:1px solid var(--border)"';

const aujourdhui = () => new Date().toISOString().slice(0, 10);

function optionsComptes(vide = null) {
  return (vide ? `<option value="">${esc(vide)}</option>` : '') +
    comptes().map(c => `<option value="${c.id}">${esc(c.nom)}</option>`).join('');
}

/** Recharge le portefeuille et les trois panneaux après une écriture au journal. */
async function rafraichir() {
  await reload();
  loadTransactions();
  loadJournalPanels();
}

export function loadJournalPanels() {
  renderSansJournal();
  renderProgrammes();
}

// ══════════════════════════════════════════════════════════════
// PRIX DE REVIENT À RECONSTITUER
// ══════════════════════════════════════════════════════════════
let sansJournal = [];

async function renderSansJournal() {
  const zone = el('txSansJournal');
  const bloc = el('txSansJournalBox');
  if (!zone) return;

  try {
    sansJournal = (await api.getPositionsSansJournal()).positions || [];
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  // Rien à reconstituer : le panneau n'a aucune raison d'occuper l'écran.
  bloc.hidden = !sansJournal.length;
  if (!sansJournal.length) return;

  el('txSansJournalCount').textContent = sansJournal.length;
  if (!el('txOuvertureDate').value) el('txOuvertureDate').value = aujourdhui();
  zone.innerHTML =
    `<thead><tr>
      <th ${TH}>Position</th><th ${TH}>Compte</th>
      <th ${TH} style="text-align:right">Quantité</th>
      <th ${TH} style="text-align:right">PRU</th>
      <th ${TH}>Date d'achat</th><th ${TH}></th>
    </tr></thead><tbody>` +
    sansJournal.map(p => `<tr>
      <td ${TD}>${esc(p.nom)}</td>
      <td ${TD}>${badgeType(p.compte_type)} ${esc(p.compte || '')}</td>
      <td ${TD} style="text-align:right">${fmtQty(p.quantite, 8)}</td>
      <td ${TD} style="text-align:right">${fmtDevise(p.pru, p.devise)}</td>
      <td ${TD}><input type="date" id="ouv-${p.id}" value="${aujourdhui()}"
          style="padding:3px 6px;font-size:12px;width:140px"></td>
      <td ${TD}><button class="btn btn-mini" onclick="reconstituerOuverture(${p.id})"
          title="Enregistre l'achat d'ouverture au taux de change de cette date">Reconstituer</button></td>
    </tr>`).join('') + '</tbody>';
}

export async function reconstituerOuverture(positionId) {
  const date = el(`ouv-${positionId}`)?.value;
  if (!date) { alert('Choisissez la date de l\'achat.'); return; }
  try {
    await api.ouvrirPosition(positionId, { date });
    await rafraichir();
  } catch (e) {
    alert('Reconstitution impossible : ' + e.message);
  }
}

export async function reconstituerToutes() {
  const date = el('txOuvertureDate').value;
  if (!date) { alert('Choisissez la date à appliquer.'); return; }
  if (!confirm(`Enregistrer l'achat d'ouverture de ${sansJournal.length} position(s) `
             + `au ${fmtDate(date)} ? Vous pourrez corriger chaque date ensuite.`)) return;

  const echecs = [];
  for (const position of sansJournal) {
    try {
      await api.ouvrirPosition(position.id, { date });
    } catch (e) {
      echecs.push(`${position.nom} : ${e.message}`);
    }
  }
  await rafraichir();
  if (echecs.length) alert('Certaines positions n\'ont pas pu être reconstituées :\n' + echecs.join('\n'));
}

// ══════════════════════════════════════════════════════════════
// VERSEMENTS PROGRAMMÉS
// ══════════════════════════════════════════════════════════════
let programmes = [];
let programmeEnEdition = null;

async function renderProgrammes() {
  const zone = el('txProgrammes');
  if (!zone) return;
  try {
    programmes = (await api.getProgrammes()).programmes || [];
  } catch (e) {
    zone.innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }

  if (!programmes.length) {
    zone.innerHTML = '<tbody><tr><td class="table-empty">Aucun versement programmé. '
      + 'Déclarez un virement récurrent et ses échéances s\'inscriront seules au journal, '
      + 'y compris celles passées depuis la date de début.</td></tr></tbody>';
    return;
  }

  zone.innerHTML =
    `<thead><tr>
      <th ${TH}>Compte</th><th ${TH}>Type</th>
      <th ${TH} style="text-align:right">Montant</th>
      <th ${TH}>Rythme</th><th ${TH}>Prochaine</th><th ${TH}>État</th><th ${TH}>Actions</th>
    </tr></thead><tbody>` +
    programmes.map(p => `<tr${p.actif ? '' : ' style="opacity:.55"'}>
      <td ${TD}>${badgeType(p.compte_type)} ${esc(p.compte || '')}</td>
      <td ${TD}><span class="tag tx-${esc(p.type)}">${esc(p.type)}</span></td>
      <td ${TD} style="text-align:right">${fmt(p.montant_eur)}</td>
      <td ${TD}>${esc(p.frequence_label)}, le ${p.jour}</td>
      <td ${TD}>${p.prochaine ? esc(fmtDate(p.prochaine)) : '<span class="muted">—</span>'}</td>
      <td ${TD}>${p.actif ? '<span class="pos">actif</span>' : '<span class="muted">en pause</span>'}</td>
      <td ${TD} class="actions">
        <button class="btn btn-mini" onclick="editProgramme(${p.id})" title="Modifier">✏️</button>
        <button class="btn btn-mini" onclick="deleteProgramme(${p.id})" title="Supprimer">🗑</button>
      </td>
    </tr>`).join('') + '</tbody>';
}

export function openProgrammeModal(id = null) {
  if (!comptes().length) { alert('Créez d\'abord un compte.'); return; }

  programmeEnEdition = id;
  const p = id ? programmes.find(x => x.id === id) : null;
  el('progModalTitle').textContent = p ? 'Modifier le versement programmé' : 'Programmer un versement';
  el('progError').textContent = '';
  el('progCompte').innerHTML = optionsComptes();

  el('progCompte').value = String(p?.account_id || Store.currentAccountId || comptes()[0].id);
  el('progType').value = p?.type || 'versement';
  el('progMontant').value = p?.montant_eur ?? '';
  el('progFrequence').value = p?.frequence || 'mensuel';
  el('progJour').value = p?.jour ?? 1;
  el('progDebut').value = p?.debut || aujourdhui();
  el('progFin').value = p?.fin || '';
  el('progNote').value = p?.note || '';
  el('progActif').checked = p ? Boolean(p.actif) : true;

  el('progModal').classList.add('open');
}

export function closeProgrammeModal() { el('progModal').classList.remove('open'); }

export async function saveProgramme() {
  const erreur = el('progError');
  erreur.textContent = '';
  const payload = {
    account_id: Number(el('progCompte').value),
    type: el('progType').value,
    montant_eur: parseNum(el('progMontant').value),
    frequence: el('progFrequence').value,
    jour: Number(el('progJour').value),
    debut: el('progDebut').value,
    fin: el('progFin').value,
    actif: el('progActif').checked,
    note: el('progNote').value.trim(),
  };
  try {
    if (programmeEnEdition) await api.updateProgramme(programmeEnEdition, payload);
    else await api.createProgramme(payload);
    closeProgrammeModal();
    await renderProgrammes();
  } catch (e) {
    erreur.textContent = e.message;
  }
}

export function editProgramme(id) { openProgrammeModal(id); }

export async function deleteProgramme(id) {
  if (!confirm('Supprimer ce versement programmé ? Les mouvements déjà inscrits au journal sont conservés.')) return;
  try {
    await api.deleteProgramme(id);
    await renderProgrammes();
  } catch (e) {
    alert('Suppression impossible : ' + e.message);
  }
}

export async function executerProgrammes() {
  const bouton = el('progRunBtn');
  bouton.disabled = true;
  try {
    const r = await api.executerProgrammes();
    alert(r.mouvements_crees
      ? `${r.mouvements_crees} mouvement(s) inscrit(s) au journal.`
      : 'Aucune échéance due : tout est déjà à jour.');
    await rafraichir();
  } catch (e) {
    alert('Exécution impossible : ' + e.message);
  }
  bouton.disabled = false;
}

// ══════════════════════════════════════════════════════════════
// IMPORT D'UN RELEVÉ
// ══════════════════════════════════════════════════════════════
let fichier = { contenu_b64: '', nom: '', analyse: null };

/** Octets d'un fichier en base64, par tranches : `apply` cale sur un gros tableau. */
async function enBase64(fichierChoisi) {
  const octets = new Uint8Array(await fichierChoisi.arrayBuffer());
  const TRANCHE = 0x8000;
  let binaire = '';
  for (let i = 0; i < octets.length; i += TRANCHE) {
    binaire += String.fromCharCode.apply(null, octets.subarray(i, i + TRANCHE));
  }
  return btoa(binaire);
}

// Une seule liste : elle construit les menus de l'étape 2 et décide de ce qui
// part au serveur. En tenir deux en parallèle, c'est oublier d'en servir une.
const CHAMPS_IMPORT = [
  ['date', 'Date', 'obligatoire'],
  ['type', 'Type d\'opération', 'sinon, le type par défaut ci-dessous'],
  ['libelle', 'Libellé', 'nom de la ligne tel que le relevé l\'écrit'],
  ['isin', 'ISIN', 'rapproche les lignes même si les noms diffèrent'],
  ['quantite', 'Quantité', ''],
  ['prix', 'Prix unitaire', 'déduit du montant s\'il manque'],
  ['devise', 'Devise', ''],
  ['taux', 'Taux de change', 'celui du jour de l\'opération, s\'il figure au relevé'],
  ['frais', 'Frais', ''],
  ['montant', 'Montant', 'pour les versements, retraits et dividendes'],
  ['credit', 'Crédit', 'relevés qui séparent les entrées des sorties'],
  ['debit', 'Débit', 'utilisé si montant et crédit sont vides'],
];

export function openImportModal() {
  if (!comptes().length) { alert('Créez d\'abord un compte où importer les mouvements.'); return; }
  fichier = { contenu_b64: '', nom: '', analyse: null };
  el('impError').textContent = '';
  el('impFichier').value = '';
  el('impCompte').innerHTML = optionsComptes();
  el('impCompte').value = String(Store.currentAccountId || comptes()[0].id);
  el('impEtape2').hidden = true;
  el('impEtape3').hidden = true;
  el('impValiderBtn').hidden = true;
  el('impModal').classList.add('open');
}

export function closeImportModal() { el('impModal').classList.remove('open'); }

/** Étape 1 : lire le fichier et laisser le serveur proposer la correspondance. */
export async function onImportFile(input) {
  const choisi = input.files?.[0];
  if (!choisi) return;
  el('impError').textContent = '';
  try {
    // Les octets bruts plutôt que le texte : un classeur est binaire, et un
    // CSV en latin-1 serait déjà abîmé par un décodage côté navigateur.
    fichier.contenu_b64 = await enBase64(choisi);
    fichier.nom = choisi.name;
    fichier.analyse = await api.analyserImport({ contenu_b64: fichier.contenu_b64 });
  } catch (e) {
    el('impError').textContent = e.message;
    el('impEtape2').hidden = true;
    return;
  }

  const a = fichier.analyse;
  el('impResume').innerHTML =
    `<strong>${esc(fichier.nom)}</strong> — ${a.nb_lignes} ligne(s), `
    + `${a.separateur === 'xlsx' ? 'classeur Excel' : `séparateur « ${a.separateur === '\t' ? 'tabulation' : esc(a.separateur)} »`}, `
    + `${a.colonnes.length} colonne(s).`;

  const options = colonne => '<option value="">— aucune —</option>' +
    a.colonnes.map((nom, i) =>
      `<option value="${i}"${a.correspondance[colonne] === i ? ' selected' : ''}>${esc(nom || `colonne ${i + 1}`)}</option>`
    ).join('');

  el('impMapping').innerHTML = CHAMPS_IMPORT.map(([cle, libelle, aide]) => `
    <div class="form-group">
      <label>${esc(libelle)}${aide ? ` <span class="muted" style="font-weight:400">(${esc(aide)})</span>` : ''}</label>
      <select id="imp-${cle}">${options(cle)}</select>
    </div>`).join('');

  el('impApercu').innerHTML =
    `<thead><tr>${a.colonnes.map(c => `<th ${TH}>${esc(c)}</th>`).join('')}</tr></thead><tbody>`
    + a.apercu.map(ligne => `<tr>${a.colonnes.map((_, i) =>
        `<td ${TD}>${esc(ligne[i] ?? '')}</td>`).join('')}</tr>`).join('')
    + '</tbody>';

  el('impEtape2').hidden = false;
  el('impEtape3').hidden = true;
  el('impValiderBtn').hidden = true;
}

function correspondanceSaisie() {
  const mapping = {};
  for (const cle of CHAMPS_IMPORT.map(([cle]) => cle)) {
    const valeur = el(`imp-${cle}`)?.value;
    if (valeur !== '' && valeur != null) mapping[cle] = Number(valeur);
  }
  return mapping;
}

const optionsImport = () => ({
  creer_positions: el('impCreerPositions').checked,
  type_defaut: el('impTypeDefaut').value,
  devise_defaut: el('impDeviseDefaut').value,
});

/** Étape 2 : montrer exactement ce qui sera écrit, sans rien écrire. */
export async function apercuImport() {
  el('impError').textContent = '';
  let r;
  try {
    r = await api.executerImport({
      contenu_b64: fichier.contenu_b64,
      account_id: Number(el('impCompte').value),
      correspondance: correspondanceSaisie(),
      options: optionsImport(),
      valider: false,
    });
  } catch (e) {
    el('impError').textContent = e.message;
    return;
  }
  afficherRapport(r);
  el('impEtape3').hidden = false;
  el('impValiderBtn').hidden = r.resume.a_importer === 0;
  el('impValiderBtn').textContent = `Importer ${r.resume.a_importer} ligne(s)`;
}

/** Étape 3 : écrire. Le même code qu'à l'aperçu, `valider` en plus. */
export async function validerImport() {
  const bouton = el('impValiderBtn');
  bouton.disabled = true;
  try {
    const r = await api.executerImport({
      contenu_b64: fichier.contenu_b64,
      account_id: Number(el('impCompte').value),
      correspondance: correspondanceSaisie(),
      options: optionsImport(),
      valider: true,
    });
    afficherRapport(r);
    bouton.hidden = true;
    await rafraichir();
    el('impError').textContent = '';
    el('impBilan').innerHTML =
      `<div class="hint-box" style="border-color:var(--green)">✓ ${r.resume.importes} ligne(s) `
      + `enregistrée(s)${r.resume.dividendes ? `, dont ${r.resume.dividendes} dividende(s) dans l'onglet Dividendes` : ''}. `
      + 'Quantités et prix de revient des lignes concernées ont été recalculés.</div>';
  } catch (e) {
    el('impError').textContent = e.message;
  }
  bouton.disabled = false;
}

function afficherRapport(r) {
  const s = r.resume;
  const puces = [
    `${s.a_importer} à importer`,
    s.dividendes ? `dont ${s.dividendes} dividende(s)` : '',
    s.alertes ? `${s.alertes} vente(s) sans achat connu` : '',
    s.doublons ? `${s.doublons} déjà enregistré(s)` : '',
    s.erreurs ? `${s.erreurs} en erreur` : '',
    s.positions_a_creer.length ? `${s.positions_a_creer.length} position(s) à créer : ${s.positions_a_creer.map(esc).join(', ')}` : '',
  ].filter(Boolean);
  el('impBilan').innerHTML = `<div class="hint-box">${s.total} ligne(s) lue(s) — ${puces.join(' · ')}.</div>`;

  const TON = { ok: 'pos', alerte: 'attention', doublon: 'muted', erreur: 'neg' };
  const ETIQUETTE = { ok: '✓', alerte: '⚠', doublon: '=', erreur: '✕' };
  el('impRapport').innerHTML =
    `<thead><tr>
      <th ${TH}>Ligne</th><th ${TH}></th><th ${TH}>Date</th><th ${TH}>Type</th>
      <th ${TH}>Libellé</th><th ${TH}>Détail</th><th ${TH}>Observation</th>
    </tr></thead><tbody>` +
    r.lignes.map(l => `<tr class="${TON[l.statut]}">
      <td ${TD}>${l.numero}</td>
      <td ${TD}>${ETIQUETTE[l.statut]}</td>
      <td ${TD}>${l.date ? esc(fmtDate(l.date)) : '<span class="muted">—</span>'}</td>
      <td ${TD}>${esc(l.type || '—')}</td>
      <td ${TD}>${esc(l.libelle || '—')}${l.position_nom && l.position_nom !== l.libelle
        ? `<span class="muted"> → ${esc(l.position_nom)}</span>` : ''}</td>
      <td ${TD}>${l.sur_ligne
        ? `${l.quantite} × ${l.prix} ${l.devise === 'EUR' ? '€' : esc(l.devise)}`
        : fmt(l.montant)}</td>
      <td ${TD} class="muted" style="font-size:12px">${esc(l.message || '')}</td>
    </tr>`).join('') + '</tbody>';
}
