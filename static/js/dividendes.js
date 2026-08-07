import { Store, typeInfo, comptes, compteById } from './state.js';
import { api } from './api.js';
import { fmt, esc, kpiCard, badgeType, destroyChart, makeChart, parseNum, fmtChart } from './core.js';
import { chartColors } from './theme.js';

let dividendeEnEdition = null;

const el = id => document.getElementById(id);

function optionsComptes(vide = null) {
  return (vide ? `<option value="">${esc(vide)}</option>` : '') +
    comptes().map(c => `<option value="${c.id}">${esc(c.nom)}</option>`).join('');
}

export function openDivModal(id = null) {
  if (!comptes().length) {
    alert('Créez d\'abord un compte pour y rattacher vos dividendes.');
    return;
  }

  dividendeEnEdition = id;
  el('divModalTitle').textContent = id ? 'Modifier le dividende' : 'Ajouter un dividende';
  el('dividendeError').textContent = '';
  el('dCompte').innerHTML = optionsComptes();

  if (!id) {
    el('dDate').value = new Date().toISOString().slice(0, 10);
    el('dCompte').value = String(Store.currentAccountId || comptes()[0].id);
    ['dNom', 'dMontant', 'dMontantNet', 'dNote'].forEach(champ => { el(champ).value = ''; });
  }

  onDividendeAccountChange();
  el('divModal').classList.add('open');
}

/** Propose les positions du compte choisi et rappelle sa fiscalité. */
export function onDividendeAccountChange() {
  const compte = compteById(el('dCompte').value);
  const noms = (compte?.positions || []).map(p => p.nom);
  el('dNomList').innerHTML = noms.map(n => `<option value="${esc(n)}">`).join('');
  el('divFiscHint').textContent = compte ? typeInfo(compte.type).resume_fiscal || '' : '';
}

export function closeDivModal() { el('divModal').classList.remove('open'); }

export async function saveDividende() {
  const erreur = el('dividendeError');
  erreur.textContent = '';

  const payload = {
    date: el('dDate').value,
    account_id: Number(el('dCompte').value),
    nom: el('dNom').value.trim(),
    montant: parseNum(el('dMontant').value),
    montant_net: el('dMontantNet').value.trim() ? parseNum(el('dMontantNet').value) : null,
    note: el('dNote').value.trim(),
  };
  if (!payload.date || !payload.nom || !payload.montant) {
    erreur.textContent = 'Date, position et montant brut sont obligatoires.';
    return;
  }

  try {
    if (dividendeEnEdition) await api.updateDividende(dividendeEnEdition, payload);
    else await api.createDividende(payload);
    closeDivModal();
    loadDividendes();
  } catch (e) {
    erreur.textContent = e.message;
  }
}

export async function deleteDividende(id) {
  if (!confirm('Supprimer ce versement ?')) return;
  try {
    await api.deleteDividende(id);
    loadDividendes();
  } catch (e) {
    alert('Suppression impossible : ' + e.message);
  }
}

export function editDividende(id) {
  const div = (Store.dividendes || []).find(d => d.id === id);
  if (!div) return;
  openDivModal(id);
  el('dDate').value = div.date;
  el('dCompte').value = String(div.account_id);
  el('dNom').value = div.nom;
  el('dMontant').value = div.montant;
  el('dMontantNet').value = div.montant_net ?? '';
  el('dNote').value = div.note || '';
  onDividendeAccountChange();
}

export async function loadDividendes() {
  const filtreCompte = el('divFilterCompte');
  const compteChoisi = filtreCompte.value;
  filtreCompte.innerHTML = optionsComptes('Tous les comptes');
  filtreCompte.value = compteChoisi;

  let d;
  try {
    d = await api.getDividendes({ annee: el('divFilterAnnee').value, account_id: compteChoisi });
  } catch (e) {
    el('divCards').innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
    return;
  }
  Store.dividendes = d.dividendes || [];

  const s = d.stats || {};
  const selecteurAnnee = el('divFilterAnnee');
  const anneeChoisie = selecteurAnnee.value;
  selecteurAnnee.innerHTML = '<option value="">Toutes années</option>' +
    (d.by_year || []).map(y => `<option value="${y.annee}">${y.annee}</option>`).join('');
  selecteurAnnee.value = anneeChoisie;

  el('divCards').innerHTML =
    kpiCard('Total perçu (brut)', fmt(s.total_brut || 0)) +
    kpiCard('Total perçu (net)', fmt(s.total_net || 0)) +
    kpiCard('Année en cours', fmt(s.annee_en_cours || 0)) +
    kpiCard('Versements', `${s.nb || 0}`, s.premier_versement ? `depuis ${s.premier_versement}` : '', 'neu');

  // ── Graphique mensuel ──
  destroyChart('chartDivMois');
  const mois = d.by_month || [];
  if (mois.length) {
    makeChart('chartDivMois', {
      type: 'bar',
      data: {
        labels: mois.map(m => m.mois),
        datasets: [{ label: 'Dividendes bruts (€)', data: mois.map(m => m.total), backgroundColor: 'rgba(63,185,80,.7)', borderRadius: 5 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, maxRotation: 45 } },
          y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtChart } },
        },
      },
    });
  }

  // ── Graphique annuel ──
  destroyChart('chartDivAnnee');
  const annees = [...(d.by_year || [])].reverse();
  if (annees.length) {
    makeChart('chartDivAnnee', {
      type: 'bar',
      data: {
        labels: annees.map(y => y.annee),
        datasets: [
          { label: 'Brut', data: annees.map(y => y.total_brut || 0), backgroundColor: 'rgba(88,166,255,.7)', borderRadius: 4 },
          { label: 'Net', data: annees.map(y => y.total_net || 0), backgroundColor: 'rgba(63,185,80,.7)', borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12 } } },
        scales: {
          x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted } },
          y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: fmtChart } },
        },
      },
    });
  }

  // ── Top positions ──
  const th = 'style="padding:6px 10px;text-align:left;color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)"';
  const td = 'style="padding:6px 10px;border-bottom:1px solid var(--border)"';
  el('divTopPos').innerHTML =
    `<thead><tr><th ${th}>Position</th><th ${th}>Compte</th><th ${th}>Total brut</th><th ${th}>Versements</th></tr></thead>` +
    `<tbody>${(d.by_pos || []).map(p => `
      <tr>
        <td ${td}>${esc(p.nom)}</td>
        <td ${td}>${badgeType(p.compte_type)} ${esc(p.compte || '')}</td>
        <td ${td} class="pos">${fmt(p.total)}</td>
        <td ${td}>${p.nb}</td>
      </tr>`).join('') || `<tr><td ${td} colspan="4" class="muted">Aucun versement enregistré</td></tr>`}</tbody>`;

  // ── TRI par position ──
  const triDiv = el('divTRI');
  const top = (d.by_pos || []).slice(0, 6);
  if (!top.length) {
    triDiv.innerHTML = '<span class="muted">Aucune donnée</span>';
  } else {
    triDiv.innerHTML = '<span class="muted">Calcul en cours…</span>';
    const resultats = await Promise.all(top.map(async p => {
      try { return { nom: p.nom, tri: (await api.getTri(p.nom, p.account_id)).tri }; }
      catch { return { nom: p.nom, tri: null }; }
    }));
    triDiv.innerHTML = resultats.map(t => `
      <div class="tri-row">
        <span>${esc(t.nom.length > 30 ? t.nom.slice(0, 30) + '…' : t.nom)}</span>
        <span class="${t.tri == null ? 'neu' : t.tri >= 0 ? 'pos' : 'neg'}" style="font-weight:700">
          ${t.tri == null ? '—' : (t.tri >= 0 ? '+' : '') + t.tri.toFixed(2) + '% TRI'}
        </span>
      </div>`).join('');
  }

  // ── Historique des versements ──
  const lignes = (d.dividendes || []).map(v => `
    <tr>
      <td ${td}>${esc(v.date)}</td>
      <td ${td}>${badgeType(v.compte_type)} ${esc(v.compte || '')}</td>
      <td ${td}>${esc(v.nom)}</td>
      <td ${td} class="pos">${fmt(v.montant)}</td>
      <td ${td} class="pos">${v.montant_net ? fmt(v.montant_net) : '<span class="muted">—</span>'}</td>
      <td ${td} class="muted" style="font-size:12px">${esc(v.note || '')}</td>
      <td ${td} class="actions">
        <button class="btn btn-mini" onclick="editDividende(${v.id})">✏️</button>
        <button class="btn btn-mini" onclick="deleteDividende(${v.id})">🗑</button>
      </td>
    </tr>`).join('');

  el('divTable').innerHTML =
    `<thead><tr>
      <th ${th}>Date</th><th ${th}>Compte</th><th ${th}>Position</th>
      <th ${th}>Brut</th><th ${th}>Net</th><th ${th}>Note</th><th ${th}>Actions</th>
    </tr></thead><tbody>${lignes || `
      <tr><td colspan="7" class="table-empty">Aucun dividende enregistré — cliquez sur « + Dividende ».</td></tr>`}
    </tbody>`;
}
