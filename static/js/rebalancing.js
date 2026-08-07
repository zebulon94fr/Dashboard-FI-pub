import { typeInfo, comptes, totalPortefeuille } from './state.js';
import { api } from './api.js';
import { fmt, esc, kpiCard, emptyState, destroyChart, makeChart } from './core.js';
import { chartColors } from './theme.js';
import { couleursComptes } from './colors.js';

// Cibles en cours d'édition : {account_id: pourcentage}. Initialisées depuis le serveur.
let cibles = {};

const el = id => document.getElementById(id);
const euro = v => Math.round(v).toLocaleString('fr-FR') + ' €';

function chargerCibles() {
  cibles = Object.fromEntries(comptes().map(c => [c.id, c.cible_pct || 0]));
}

export function renderRebalancing() {
  const liste = comptes();
  if (!liste.length) {
    el('rbKpis').innerHTML = '';
    el('rbCiblesForm').innerHTML = emptyState(
      'Aucun compte à équilibrer',
      'Créez au moins deux comptes pour définir une allocation cible.',
      '<button class="btn primary" onclick="openAccountModal()">+ Créer un compte</button>');
    el('rbTableEcarts').innerHTML = '';
    el('rbOrdres').innerHTML = '';
    destroyChart('rbChartAlloc');
    return;
  }

  chargerCibles();

  const total = totalPortefeuille();
  const reelle = Object.fromEntries(liste.map(c => [c.id, total ? (c.valorisation / total) * 100 : 0]));

  const ecartTotal = liste.reduce((s, c) => s + Math.abs((cibles[c.id] || 0) - reelle[c.id]), 0);
  const score = Math.max(0, Math.round(100 - ecartTotal / 2));
  const driftMax = liste.reduce((mx, c) => Math.max(mx, Math.abs((cibles[c.id] || 0) - reelle[c.id])), 0);

  el('rbKpis').innerHTML =
    kpiCard('Patrimoine total', fmt(total), `${liste.length} compte${liste.length > 1 ? 's' : ''}`, 'neu') +
    kpiCard('Score d\'équilibre', `${score} / 100`,
      score >= 85 ? 'Bien équilibré' : score >= 65 ? 'Légèrement déséquilibré' : 'Rééquilibrage conseillé',
      score >= 85 ? 'pos' : score >= 65 ? 'neu' : 'neg') +
    kpiCard('Écart maximum', `${driftMax.toFixed(1)} %`, 'par rapport à la cible', 'neu') +
    kpiCard('Comptes alimentés', `${liste.filter(c => c.valorisation > 0).length} / ${liste.length}`, '', 'neu');

  const couleurs = couleursComptes(liste);
  el('rbCiblesForm').innerHTML = liste.map((c, i) => `
    <div class="rb-row">
      <span class="rb-label">${esc(typeInfo(c.type).icone)} ${esc(c.nom)}</span>
      <input type="range" min="0" max="100" step="1" value="${cibles[c.id] || 0}"
             id="rb_slider_${c.id}" oninput="rbSliderChange(${c.id}, this.value)"
             style="accent-color:${couleurs[i]}">
      <span class="rb-value" id="rb_val_${c.id}" style="color:${couleurs[i]}">${cibles[c.id] || 0} %</span>
      <span class="rb-real">réel : ${reelle[c.id].toFixed(1)} %</span>
    </div>`).join('');

  majTotalCibles();
  rbCalculer();
}

function majTotalCibles() {
  const total = comptes().reduce((s, c) => s + (cibles[c.id] || 0), 0);
  const element = el('rbTotalCibles');
  element.textContent = `${total} %`;
  element.className = Math.abs(total - 100) <= 0.01 ? 'pos' : 'neg';
}

export function rbSliderChange(accountId, valeur) {
  cibles[accountId] = parseInt(valeur) || 0;
  el(`rb_val_${accountId}`).textContent = `${cibles[accountId]} %`;
  majTotalCibles();
  rbCalculer();
}

export async function rbSauvegarderCibles() {
  const btn = event?.target;
  const texte = btn?.textContent;
  try {
    await api.saveCibles(cibles);
    for (const c of comptes()) c.cible_pct = cibles[c.id] || 0;
    if (btn) {
      btn.textContent = '✓ Sauvegardé';
      setTimeout(() => { btn.textContent = texte; }, 1500);
    }
  } catch (e) {
    alert('Sauvegarde impossible : ' + e.message);
  }
}

export function rbCalculer() {
  const liste = comptes();
  if (!liste.length) return;

  const total = totalPortefeuille();
  const apport = parseFloat((el('rbApport')?.value || '0').replace(',', '.')) || 0;
  const seuil = parseFloat(el('rbSeuil')?.value || '5');
  const totalCible = total + apport;
  const couleurs = couleursComptes(liste);
  const reelle = Object.fromEntries(liste.map(c => [c.id, total ? (c.valorisation / total) * 100 : 0]));

  // ── Graphique réel vs cible ──
  makeChart('rbChartAlloc', {
    type: 'bar',
    data: {
      labels: liste.map(c => c.nom),
      datasets: [
        { label: 'Réel %', data: liste.map(c => +reelle[c.id].toFixed(1)), backgroundColor: couleurs.map(c => c + '99'), borderRadius: 4 },
        { label: 'Cible %', data: liste.map(c => cibles[c.id] || 0), backgroundColor: 'rgba(0,0,0,0)', borderColor: couleurs, borderWidth: 2, borderRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: chartColors().muted, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { color: chartColors().muted, font: { size: 10 }, callback: v => v + '%' }, grid: { color: chartColors().grid } },
      },
    },
  });

  // ── Tableau des écarts ──
  const th = 'style="padding:10px 14px;text-align:left;color:var(--muted);font-weight:500;white-space:nowrap;border-bottom:1px solid var(--border);font-size:12px"';
  const td = 'style="padding:10px 14px;border-bottom:1px solid var(--border);white-space:nowrap;font-size:13px"';

  const mouvements = [];
  const lignes = liste.map((c, i) => {
    const cible = cibles[c.id] || 0;
    const ecartPts = cible - reelle[c.id];
    const montantCible = totalCible * cible / 100;
    const ecartEur = montantCible - c.valorisation;

    let statut = '✓ Équilibré', statutCls = 'pos';
    if (Math.abs(ecartPts) >= seuil) {
      statut = ecartPts > 0 ? '↑ Sous-pondéré' : '↓ Sur-pondéré';
      statutCls = 'neg';
      mouvements.push({ compte: c, couleur: couleurs[i], ecartEur, cible, reel: reelle[c.id], montantCible });
    }

    return `<tr>
      <td ${td}><span class="dot-legend" style="background:${couleurs[i]}"></span>${esc(c.nom)}</td>
      <td ${td} style="text-align:right">${fmt(c.valorisation)}</td>
      <td ${td} style="text-align:right">${reelle[c.id].toFixed(1)} %</td>
      <td ${td} style="text-align:right;font-weight:600">${cible} %</td>
      <td ${td} style="text-align:right" class="${ecartPts > 0 ? 'pos' : 'neg'}">${ecartPts > 0 ? '+' : ''}${ecartPts.toFixed(1)} pts</td>
      <td ${td} style="text-align:right" class="${ecartEur > 0 ? 'pos' : 'neg'}">${ecartEur > 0 ? '+' : ''}${euro(ecartEur)}</td>
      <td ${td} style="text-align:center" class="${statutCls}">${statut}</td>
    </tr>`;
  }).join('');

  el('rbTableEcarts').innerHTML = `<thead><tr>
      <th ${th}>Compte</th>
      <th ${th} style="text-align:right">Valeur actuelle</th>
      <th ${th} style="text-align:right">Alloc. réelle</th>
      <th ${th} style="text-align:right">Cible</th>
      <th ${th} style="text-align:right">Écart (pts)</th>
      <th ${th} style="text-align:right">Écart (€)</th>
      <th ${th} style="text-align:center">Statut</th>
    </tr></thead><tbody>${lignes}</tbody>`;

  renderMouvements(mouvements, seuil, apport);
}

function renderMouvements(mouvements, seuil, apport) {
  const conteneur = el('rbOrdres');
  const info = el('rbOrdresInfo');

  if (!mouvements.length) {
    conteneur.innerHTML = `<div class="table-empty">✓ Portefeuille équilibré — aucun mouvement requis au seuil de ${seuil} %.</div>`;
    info.textContent = '';
    return;
  }
  info.textContent = `${mouvements.length} compte${mouvements.length > 1 ? 's' : ''} à rééquilibrer`;

  const achats = mouvements.filter(m => m.ecartEur > 0).sort((a, b) => b.ecartEur - a.ecartEur);
  const ventes = mouvements.filter(m => m.ecartEur < 0).sort((a, b) => a.ecartEur - b.ecartEur);

  const carte = (m, sens) => {
    const positions = (m.compte.positions || [])
      .filter(p => p.valorisation > 0)
      .sort((a, b) => sens === 'achat'
        ? (b.pv_pct || 0) - (a.pv_pct || 0)     // renforcer ce qui performe
        : (b.pv_latent || 0) - (a.pv_latent || 0))  // alléger les plus grosses plus-values
      .slice(0, 3)
      .map(p => esc(p.nom));

    return `<div class="rb-card" style="border-left-color:var(--${sens === 'achat' ? 'green' : 'red'})">
      <div class="rb-card-head">
        <span><span class="dot-legend" style="background:${m.couleur}"></span>${esc(m.compte.nom)}</span>
        <span class="${sens === 'achat' ? 'pos' : 'neg'}" style="font-size:16px;font-weight:700">
          ${sens === 'achat' ? '+' : '−'}${euro(Math.abs(m.ecartEur))}
        </span>
      </div>
      <div class="rb-card-body">
        Allocation réelle : <strong>${m.reel.toFixed(1)} %</strong> → cible : <strong>${m.cible} %</strong><br>
        Valeur actuelle : ${euro(m.compte.valorisation)} → objectif : ${euro(m.montantCible)}
      </div>
      ${positions.length ? `<div class="rb-card-hint">${sens === 'achat' ? 'Renforcer' : 'Alléger'} : ${positions.join(', ')}</div>` : ''}
      ${sens === 'vente' ? avertissementVente(m.compte) : ''}
    </div>`;
  };

  const totalAchat = achats.reduce((s, m) => s + Math.abs(m.ecartEur), 0);
  const totalVente = ventes.reduce((s, m) => s + Math.abs(m.ecartEur), 0);

  conteneur.innerHTML = `
    <div class="rb-columns">
      <div>
        ${achats.length ? '<div class="rb-col-title pos">Apports / achats</div>' : ''}
        ${achats.map(m => carte(m, 'achat')).join('')}
      </div>
      <div>
        ${ventes.length ? '<div class="rb-col-title neg">Allègements / ventes</div>'
          : '<div class="table-empty">Aucune vente requise — rééquilibrage par apport seul.</div>'}
        ${ventes.map(m => carte(m, 'vente')).join('')}
      </div>
    </div>
    <div class="rb-summary">
      <div><div class="rb-summary-label">Total à investir</div><div class="pos rb-summary-value">+${euro(totalAchat)}</div></div>
      <div><div class="rb-summary-label">Total à alléger</div><div class="neg rb-summary-value">−${euro(totalVente)}</div></div>
      <div><div class="rb-summary-label">Apport encore nécessaire</div><div class="rb-summary-value">${euro(Math.max(0, totalAchat - totalVente - apport))}</div></div>
    </div>`;
}

/** Rappelle la contrainte fiscale propre à l'enveloppe avant de vendre. */
function avertissementVente(compte) {
  const messages = {
    pea: 'Sur un PEA, privilégiez un arbitrage interne : un retrait avant 5 ans clôture le plan.',
    av: 'Sur une assurance vie, un arbitrage entre supports n\'est pas imposable — contrairement à un rachat.',
    per: 'Un PER est bloqué jusqu\'à la retraite : rééquilibrez par arbitrage interne plutôt que par retrait.',
    crypto: 'Une conversion en euros déclenche l\'imposition ; un échange entre cryptoactifs, non.',
    metaux: 'La revente de métaux est taxée dès le premier euro : vérifiez la durée de détention.',
  };
  const message = messages[compte.type];
  return message ? `<div class="rb-card-warn">⚠ ${esc(message)}</div>` : '';
}
