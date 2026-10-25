// Calendrier fiscal, alertes de portefeuille et faits marquants de la Vue
// d'ensemble. Tout est dérivé de données déjà disponibles : dates d'ouverture
// des comptes, seuils du catalogue, allocations cibles et agrégats /api/stats.
import { Store, typeInfo, comptes, toutesPositions } from './state.js';
import { fmt, fmtP, fmtDate, esc } from './core.js';

const el = id => document.getElementById(id);

const JOUR = 86400000;
const PREAVIS_JOURS = 90;      // fenêtre d'alerte autour d'un cap fiscal
const SEUIL_BAISSE = -0.20;    // moins-value latente signalée sur une ligne
const SEUIL_PLAFOND = 0.90;    // remplissage d'une enveloppe plafonnée signalé

/** Taux de remplissage, sans signe ni décimale : « 28 % » et non « +28,17% ». */
const partPct = v => Math.round(v * 100) + ' %';

/** Ce que le franchissement du seuil apporte, par enveloppe. */
const APRES_SEUIL = {
  pea: 'Les retraits sont désormais exonérés d\'impôt sur le revenu : seuls les 17,2 % de prélèvements sociaux restent dus, et un retrait partiel ne clôture plus le plan.',
  av: 'L\'abattement annuel de 4 600 € (9 200 € en couple) et le taux réduit de 7,5 % s\'appliquent désormais aux gains rachetés.',
  metaux: 'Au régime des plus-values réelles, l\'abattement pour durée de détention atteint 100 % : la cession est exonérée.',
};

/** Ce que coûte une sortie avant le seuil, par enveloppe. */
const AVANT_SEUIL = {
  pea: 'D\'ici là, tout retrait reste taxé à 30 % et entraîne la clôture du plan.',
  av: 'Attendre cette date fait passer l\'imposition des gains rachetés de 30 % à 7,5 % après abattement.',
  metaux: 'L\'abattement pour durée de détention atteindra alors 100 %.',
};

// ══════════════════════════════════════════════════════════════
// DATES
// ══════════════════════════════════════════════════════════════
/** Date exacte du cap fiscal d'un compte (années calendaires), ou null. */
export function dateSeuil(compte) {
  const t = typeInfo(compte.type);
  if (!t.seuil_ans || !compte.date_ouverture) return null;
  const ouverture = new Date(compte.date_ouverture);
  if (isNaN(ouverture)) return null;
  const seuil = new Date(ouverture);
  seuil.setFullYear(seuil.getFullYear() + t.seuil_ans);
  return seuil;
}

const joursAvant = date => Math.ceil((date.getTime() - Date.now()) / JOUR);

const jourJ = date => date.toLocaleDateString('fr-FR');

/** Durée lisible à partir d'un nombre de jours : « 12 jours », « 5 mois », « 2 ans et 3 mois ». */
function delai(jours) {
  const abs = Math.abs(jours);
  if (abs < 31) return `${abs} jour${abs > 1 ? 's' : ''}`;
  if (abs < 365) {
    const mois = Math.max(1, Math.round(abs / 30.44));
    return `${mois} mois`;
  }
  let ans = Math.floor(abs / 365.25);
  let mois = Math.round((abs - ans * 365.25) / 30.44);
  if (mois >= 12) { ans += 1; mois = 0; }
  const libelleAns = `${ans} an${ans > 1 ? 's' : ''}`;
  return mois ? `${libelleAns} et ${mois} mois` : libelleAns;
}

/** Horodatage SQLite (UTC, séparateur espace) converti en Date locale. */
function parseHorodatage(valeur) {
  if (!valeur) return null;
  const texte = String(valeur).trim().replace(' ', 'T');
  const utc = /[zZ]|[+-]\d{2}:?\d{2}$/.test(texte) ? texte : texte + 'Z';
  const date = new Date(utc);
  return isNaN(date) ? null : date;
}

// ══════════════════════════════════════════════════════════════
// ALERTES
// ══════════════════════════════════════════════════════════════
/**
 * Construit la liste des alertes actives. Chaque entrée porte un ton
 * (good / warn / danger / info) qui détermine sa couleur.
 */
function construireAlertes() {
  const alertes = [];
  const liste = comptes();

  // ── Caps fiscaux : 90 jours avant, 90 jours après ──────────
  for (const c of liste) {
    const t = typeInfo(c.type);
    const date = dateSeuil(c);
    if (!date) continue;
    const jours = joursAvant(date);

    if (jours <= 0 && jours > -PREAVIS_JOURS) {
      alertes.push({
        ton: 'good', icone: '🎉',
        titre: `${c.nom} — seuil de ${t.seuil_ans} ans franchi le ${jourJ(date)}`,
        texte: APRES_SEUIL[c.type] || 'Le régime fiscal favorable de cette enveloppe s\'applique désormais.',
      });
    } else if (jours > 0 && jours <= PREAVIS_JOURS) {
      alertes.push({
        ton: 'warn', icone: '⏳',
        titre: `${c.nom} — seuil de ${t.seuil_ans} ans dans ${delai(jours)}, le ${jourJ(date)}`,
        texte: AVANT_SEUIL[c.type] || 'Le régime fiscal de cette enveloppe change à cette date.',
      });
    }
  }

  // ── Dérive de l'allocation cible ───────────────────────────
  // Les cibles vivent sur les classes d'actifs, pas sur les enveloppes : c'est
  // le serveur qui les compare, bandes de tolérance comprises.
  const derive = Store.STATS?.derive_classes;
  if (derive?.cibles_definies) {
    if (!derive.cibles_valides) {
      alertes.push({
        ton: 'info', icone: '⚖',
        titre: 'Allocations cibles incomplètes',
        texte: `Vos cibles par classe d'actifs totalisent ${derive.total_cibles.toFixed(0)} % `
             + 'au lieu de 100 %. Tant qu\'elles ne bouclent pas, les écarts de l\'onglet '
             + 'Rebalancing ne veulent rien dire.',
      });
    } else if (derive.hors_bande.length) {
      const detail = derive.hors_bande.slice(0, 3).map(c =>
        `${esc(c.label)} ${c.statut === 'sous_pondere' ? 'sous' : 'sur'}-pondéré de ${Math.abs(c.ecart_pts).toFixed(1)} pts`).join(', ');
      const reste = derive.hors_bande.length - 3;
      alertes.push({
        ton: 'warn', icone: '⚖',
        titre: `${derive.hors_bande.length} classe${derive.hors_bande.length > 1 ? 's' : ''} d'actifs hors bande de tolérance`,
        texte: `${detail}${reste > 0 ? `, et ${reste} autre${reste > 1 ? 's' : ''}` : ''}. `
             + 'L\'onglet Rebalancing calcule les montants à arbitrer, apport en priorité.',
      });
    }
  }

  // ── Plafond d'enveloppe en vue ─────────────────────────────
  // Un dépassement n'est pas qu'un chiffre : sur un PEA, il expose à la
  // clôture du plan. Mieux vaut le voir venir que le découvrir.
  for (const groupe of groupesPlafond().filter(g => g.verses >= g.plafond * SEUIL_PLAFOND)) {
    const depasse = groupe.verses >= groupe.plafond;
    const titre = groupe.detenteur
      ? `${typeInfo(groupe.type).label} de ${groupe.detenteur}`
      : groupe.noms.join(', ');
    alertes.push({
      ton: depasse ? 'danger' : 'warn', icone: '🚧',
      titre: depasse
        ? `${esc(titre)} : plafond de versements dépassé`
        : `${esc(titre)} : ${partPct(groupe.verses / groupe.plafond)} du plafond de versements`,
      texte: `${fmt(groupe.verses)} versés sur ${fmt(groupe.plafond)} autorisés. `
           + (depasse
             ? 'Un versement au-delà du plafond expose à la clôture du plan : régularisez auprès de l\'établissement.'
             : `Il reste ${fmt(groupe.plafond - groupe.verses)} à verser. `
               + 'Les retraits ne libèrent pas de place : le plafond porte sur les versements cumulés.'),
    });
  }

  // ── Taux de change jamais confirmé ─────────────────────────
  const fxDouteux = toutesPositions().filter(p =>
    p.devise && p.devise !== 'EUR' && Number(p.taux_change) === 1 && (p.valorisation || 0) > 0);
  if (fxDouteux.length) {
    alertes.push({
      ton: 'danger', icone: '💱',
      titre: `${fxDouteux.length} position${fxDouteux.length > 1 ? 's' : ''} valorisée${fxDouteux.length > 1 ? 's' : ''} à 1:1 avec l'euro`,
      texte: `${fxDouteux.slice(0, 3).map(p => `${esc(p.nom)} (${esc(p.devise)})`).join(', ')}`
           + `${fxDouteux.length > 3 ? `, et ${fxDouteux.length - 3} autre${fxDouteux.length - 3 > 1 ? 's' : ''}` : ''}. `
           + 'Aucun taux de change n\'a encore été récupéré pour ces devises : actualisez les cours, '
           + 'la valorisation en euros est fausse jusque-là.',
    });
  }

  // ── Cours jamais récupérés ou figés (serveur) ──────────────
  const stale = Store.STATS?.stale || [];
  const jamais = stale.filter(p => !p.dernier_cours);
  const figes = stale.filter(p => p.dernier_cours);

  if (jamais.length) {
    alertes.push({
      ton: 'danger', icone: '🔌',
      titre: `${jamais.length} ticker${jamais.length > 1 ? 's' : ''} sans aucun cours récupéré`,
      texte: `${jamais.slice(0, 3).map(p => `${esc(p.nom)} — ${esc(p.compte)}`).join(', ')}`
           + `${jamais.length > 3 ? `, et ${jamais.length - 3} autre${jamais.length - 3 > 1 ? 's' : ''}` : ''}. `
           + 'Vérifiez l\'orthographe du ticker sur finance.yahoo.com — le cours saisi à la main reste utilisé en attendant.',
    });
  }
  if (figes.length) {
    const plusAncien = parseHorodatage(figes[0].dernier_cours);
    alertes.push({
      ton: 'warn', icone: '🕰',
      titre: `${figes.length} cours figé${figes.length > 1 ? 's' : ''} depuis plus de 5 jours`,
      texte: `${figes.slice(0, 3).map(p => esc(p.nom)).join(', ')}`
           + `${figes.length > 3 ? `, et ${figes.length - 3} autre${figes.length - 3 > 1 ? 's' : ''}` : ''}`
           + `${plusAncien ? ` — le plus ancien remonte au ${jourJ(plusAncien)}` : ''}. `
           + 'Titre suspendu, radié, ou ticker devenu invalide.',
    });
  }

  // ── Positions en forte moins-value ─────────────────────────
  const baisses = toutesPositions()
    .filter(p => (p.pru || 0) > 0 && (p.valorisation || 0) > 0 && (p.pv_pct || 0) <= SEUIL_BAISSE)
    .sort((a, b) => (a.pv_pct || 0) - (b.pv_pct || 0));
  if (baisses.length) {
    alertes.push({
      ton: 'danger', icone: '📉',
      titre: `${baisses.length} position${baisses.length > 1 ? 's' : ''} à plus de 20 % de moins-value latente`,
      texte: `${baisses.slice(0, 3).map(p => `${esc(p.nom)} ${fmtP(p.pv_pct)}`).join(', ')}`
           + `${baisses.length > 3 ? `, et ${baisses.length - 3} autre${baisses.length - 3 > 1 ? 's' : ''}` : ''}. `
           + 'Sur un compte-titres, ces moins-values s\'imputent sur vos plus-values de l\'année si elles sont réalisées.',
    });
  }

  return alertes;
}

export function renderAlertes() {
  const zone = el('overviewAlertes');
  if (!zone) return;

  const alertes = construireAlertes();
  if (!alertes.length) { zone.innerHTML = ''; return; }

  const ordre = { danger: 0, warn: 1, good: 2, info: 3 };
  alertes.sort((a, b) => ordre[a.ton] - ordre[b.ton]);

  zone.innerHTML = alertes.map(a => `
    <div class="alert ${a.ton}">
      <span class="alert-icon" aria-hidden="true">${a.icone}</span>
      <div class="alert-body">
        <div class="alert-title">${esc(a.titre)}</div>
        <div class="alert-text">${a.texte}</div>
      </div>
    </div>`).join('');
}

// ══════════════════════════════════════════════════════════════
// CALENDRIER FISCAL
// ══════════════════════════════════════════════════════════════
/**
 * Jauge de remplissage d'une enveloppe plafonnée.
 *
 * Le plafond porte sur les versements cumulés enregistrés au journal, et non
 * sur la valorisation : un PEA de 160 000 € dont 100 000 € ont été versés
 * reste dans les clous. Sans aucun versement enregistré, mieux vaut le dire
 * que d'afficher un rassurant 0 %.
 */
/**
 * Enveloppes plafonnées, regroupées par type et par détenteur.
 *
 * Un plafond se compte par personne : deux PEA dans un foyer, ce sont deux
 * fois 150 000 €. Les additionner sur une seule jauge annoncerait un
 * dépassement là où chacun est encore dans les clous.
 */
function groupesPlafond() {
  const groupes = new Map();
  for (const c of comptes().filter(x => x.plafond > 0)) {
    const cle = `${c.type}|${c.detenteur || ''}`;
    if (!groupes.has(cle)) {
      groupes.set(cle, { type: c.type, detenteur: c.detenteur || '', plafond: c.plafond,
                         verses: c.versements_detenteur ?? c.versements ?? 0, noms: [] });
    }
    groupes.get(cle).noms.push(c.nom);
  }
  return [...groupes.values()];
}

function lignePlafond(groupe) {
  const t = typeInfo(groupe.type);
  const verses = groupe.verses || 0;
  const plafond = groupe.plafond;
  const titre = groupe.detenteur
    ? `${t.label} — ${groupe.detenteur}`
    : groupe.noms.join(', ');
  const nom = `<span class="cal-name">${esc(t.icone)} ${esc(titre)}</span>`;

  if (!verses) {
    return `<div class="cal-row">${nom}
      <span class="cal-when neu">—</span>
      <span class="cal-sub">Plafond de ${fmt(plafond)} non suivi : aucun versement n'est enregistré
        au journal. Saisissez-les dans l'onglet Mouvements.</span>
    </div>`;
  }

  const part = verses / plafond;
  const depasse = part >= 1;
  const proche = part >= SEUIL_PLAFOND;
  const ton = depasse ? 'neg' : proche ? 'neg' : 'pos';
  const couleur = depasse ? 'var(--red)' : proche ? 'var(--yellow)' : t.couleur;
  const reste = plafond - verses;

  return `<div class="cal-row">${nom}
    <span class="cal-when ${ton}">${depasse ? '⚠ dépassé' : partPct(part)}</span>
    <span class="cal-sub">${fmt(verses)} versés sur ${fmt(plafond)} —
      ${depasse ? `dépassement de ${fmt(-reste)}` : `il reste ${fmt(reste)}`}</span>
    <span class="cal-bar"><span style="width:${Math.min(100, part * 100).toFixed(1)}%;background:${couleur}"></span></span>
  </div>`;
}

export function renderCalendrier() {
  const zone = el('overviewCalendrier');
  if (!zone) return;

  const avecSeuil = comptes().filter(c => typeInfo(c.type).seuil_ans);
  const avecPlafond = groupesPlafond();
  if (!avecSeuil.length && !avecPlafond.length) {
    zone.innerHTML = '<div class="table-empty">Aucune de vos enveloppes n\'a de seuil de durée '
                   + '(le PEA, l\'assurance vie et les métaux précieux en ont un).</div>';
    return;
  }

  const lignes = avecSeuil
    .map(c => ({ compte: c, t: typeInfo(c.type), date: dateSeuil(c) }))
    .sort((a, b) => {
      if (!a.date) return 1;
      if (!b.date) return -1;
      return a.date - b.date;
    })
    .map(({ compte, t, date }) => {
      if (!date) {
        return `<div class="cal-row">
          <span class="cal-name">${esc(t.icone)} ${esc(compte.nom)}</span>
          <span class="cal-when neu">— </span>
          <span class="cal-sub">Date d'ouverture non renseignée : impossible de dater le seuil de ${t.seuil_ans} ans.
            Renseignez-la via ✏️ Modifier sur la page du compte.</span>
        </div>`;
      }

      const jours = joursAvant(date);
      const atteint = jours <= 0;
      const ecoule = Math.min(1, Math.max(0, 1 - jours / (t.seuil_ans * 365.25)));
      const ton = atteint ? 'pos' : jours <= PREAVIS_JOURS ? 'neg' : 'neu';
      const couleur = atteint ? 'var(--green)' : jours <= PREAVIS_JOURS ? 'var(--yellow)' : t.couleur;

      return `<div class="cal-row">
        <span class="cal-name">${esc(t.icone)} ${esc(compte.nom)}</span>
        <span class="cal-when ${ton}">${atteint ? '✓ acquis' : `dans ${delai(jours)}`}</span>
        <span class="cal-sub">Seuil de ${t.seuil_ans} ans ${atteint ? 'franchi' : 'atteint'} le ${jourJ(date)}</span>
        <span class="cal-bar"><span style="width:${(ecoule * 100).toFixed(1)}%;background:${couleur}"></span></span>
      </div>`;
    }).join('');

  // Une même enveloppe figure dans les deux groupes — son seuil de durée et son
  // plafond de versements —, d'où le titre qui les sépare : sans lui, le PEA
  // semble apparaître deux fois sans raison.
  const plafonds = avecPlafond.length
    ? '<div class="chart-title" style="margin:14px 0 6px">Plafonds de versement</div>'
      + avecPlafond.map(lignePlafond).join('')
    : '';
  zone.innerHTML = lignes + plafonds;
}

// ══════════════════════════════════════════════════════════════
// FAITS MARQUANTS (/api/stats)
// ══════════════════════════════════════════════════════════════
function ligneFait(nom, sousTitre, valeur, valeurCls) {
  return `<div class="fact-row">
    <span class="fact-name">${esc(nom)}<div class="fact-sub">${esc(sousTitre)}</div></span>
    <span class="fact-val ${valeurCls}">${valeur}</span>
  </div>`;
}

export function renderFaits() {
  const zone = el('overviewFaits');
  if (!zone) return;

  const s = Store.STATS;
  if (!s) {
    zone.innerHTML = '<div class="table-empty">Agrégats indisponibles — le serveur n\'a pas répondu.</div>';
    return;
  }

  const gains = (s.top_pv || []).filter(p => (p.pv_latent || 0) > 0).slice(0, 3);
  const pertes = (s.worst_pv || []).filter(p => (p.pv_latent || 0) < 0).slice(0, 3);

  const blocs = [];

  if (gains.length) {
    blocs.push('<div class="fact-title pos">Plus fortes plus-values latentes</div>'
      + gains.map(p => ligneFait(p.nom, p.compte, `${fmt(p.pv_latent)} <span class="fact-sub">${fmtP(p.pv_pct)}</span>`, 'pos')).join(''));
  }
  if (pertes.length) {
    blocs.push('<div class="fact-title neg">Plus fortes moins-values latentes</div>'
      + pertes.map(p => ligneFait(p.nom, p.compte, `${fmt(p.pv_latent)} <span class="fact-sub">${fmtP(p.pv_pct)}</span>`, 'neg')).join(''));
  }

  const journees = [];
  if (s.best_day) journees.push(ligneFait('Meilleure journée', fmtDate(s.best_day.date), fmt(s.best_day.delta), 'pos'));
  if (s.worst_day) journees.push(ligneFait('Pire journée', fmtDate(s.worst_day.date), fmt(s.worst_day.delta), 'neg'));
  if (journees.length) blocs.push('<div class="fact-title">Journées extrêmes</div>' + journees.join(''));

  if (!blocs.length) {
    zone.innerHTML = '<div class="table-empty">Pas encore de quoi comparer — '
                   + 'actualisez les cours quelques jours pour construire l\'historique.</div>';
    return;
  }

  zone.innerHTML = blocs.join('')
    + `<div class="chart-hint">${s.snap_count || 0} relevé${(s.snap_count || 0) > 1 ? 's' : ''} enregistré${(s.snap_count || 0) > 1 ? 's' : ''}</div>`;
}

/** Vide les trois zones (portefeuille sans aucun compte). */
export function clearAlertes() {
  ['overviewAlertes', 'overviewCalendrier', 'overviewFaits'].forEach(id => {
    const zone = el(id);
    if (zone) zone.innerHTML = '';
  });
}
