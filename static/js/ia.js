import { typeInfo, comptes, totalPortefeuille } from './state.js';
import { api } from './api.js';
import { statutFiscal } from './accounts.js';

export function saveKey() {
  const cle = document.getElementById('apiKey').value;
  localStorage.setItem('dashboardfi_apiKey', cle);
  // Sauvegarde aussi côté serveur, pour retrouver la clé depuis un autre navigateur.
  api.saveSettings(cle).catch(() => {});
}

/** Résumé anonymisé du portefeuille : structure, pas d'identifiants de compte. */
function resumePortefeuille() {
  const passif = comptes().filter(c => c.passif).reduce((s, c) => s + (c.valorisation || 0), 0);
  return {
    actifBrut: totalPortefeuille().toFixed(2),
    passif: passif.toFixed(2),
    patrimoineNet: (totalPortefeuille() - passif).toFixed(2),
    comptes: comptes().map(c => ({
      nom: c.nom,
      enveloppe: typeInfo(c.type).nom_complet || typeInfo(c.type).label,
      estPassif: c.passif || undefined,
      anciennete: statutFiscal(c).texte,
      valorisation: (c.valorisation || 0).toFixed(2),
      investi: (c.investi || 0).toFixed(2),
      performance: `${((c.pv_pct || 0) * 100).toFixed(1)}%`,
      positions: (c.positions || []).map(p => ({
        nom: p.nom,
        valorisation: p.valorisation,
        performance: `${((p.pv_pct || 0) * 100).toFixed(1)}%`,
        secteur: p.secteur || undefined,
        zone: p.zone || undefined,
      })),
    })),
  };
}

const PROMPTS = {
  global: 'Analyse globale de ce portefeuille français. Donne un diagnostic concis, les forces, les faiblesses, puis 3 à 5 recommandations concrètes.',
  fiscal: 'Analyse la répartition entre enveloppes fiscales françaises (PEA, CTO, PER, assurance vie, métaux, cryptoactifs) et identifie les optimisations possibles.',
  risk: 'Analyse les risques de ce portefeuille : concentration, devises, secteurs, corrélations. Donne un score de risque et des recommandations.',
  diversification: 'Analyse la diversification géographique, sectorielle et par classe d\'actifs. Identifie les manques et suggère des ajouts pertinents.',
  retraite: 'Analyse ce portefeuille dans une optique retraite (France). Évalue l\'adéquation des enveloppes, l\'horizon, et suggère une stratégie.',
};

/**
 * Texte d'une réponse de l'API, ou la raison pour laquelle il n'y en a pas.
 *
 * « Réponse vide » ne disait rien de ce qui s'était passé : une erreur de
 * l'API, une réponse coupée sur la limite de longueur et une réponse sans
 * bloc de texte s'affichaient toutes de la même façon, sans rien à en tirer.
 */
export function texteReponse(reponse) {
  const blocs = Array.isArray(reponse?.content) ? reponse.content : [];
  const texte = blocs
    .filter(b => b?.type === 'text')
    .map(b => b.text || '')
    .join('')
    .trim();
  if (texte) return texte;

  const erreur = typeof reponse?.error === 'string' ? reponse.error : reponse?.error?.message;
  if (erreur) return `L'API a répondu : ${erreur}`;

  if (reponse?.stop_reason === 'max_tokens') {
    return 'La réponse a atteint la limite de longueur avant d\'avoir produit du texte. '
      + 'Réessayez — si cela se reproduit, c\'est que le budget de réponse est trop court '
      + 'pour ce portefeuille.';
  }

  const types = [...new Set(blocs.map(b => b?.type).filter(Boolean))];
  if (types.length) {
    return `Réponse sans aucun bloc de texte (blocs reçus : ${types.join(', ')}).`;
  }
  return 'Réponse vide : l\'API n\'a renvoyé aucun contenu'
    + (reponse?.stop_reason ? ` (arrêt : ${reponse.stop_reason}).` : '.');
}

export async function analyzeIA() {
  const cle = document.getElementById('apiKey').value.trim();
  const sortie = document.getElementById('iaOutput');

  if (!cle) { alert('Une clé API Anthropic est nécessaire pour cette analyse.'); return; }
  if (!comptes().length) { sortie.textContent = 'Créez d\'abord un compte et quelques positions à analyser.'; return; }

  const mode = document.querySelector('input[name=mode]:checked').value;
  sortie.className = 'ia-output loading';
  sortie.textContent = '⏳ Analyse en cours…';

  try {
    const reponse = await api.claude({
      apiKey: cle,
      model: 'claude-sonnet-5',
      // Le prompt demande un diagnostic, des forces, des faiblesses et
      // plusieurs recommandations : 1 500 jetons ne suffisaient pas toujours
      // à les tenir, et la réponse s'arrêtait en route.
      max_tokens: 4000,
      messages: [{
        role: 'user',
        content: `${PROMPTS[mode]}\n\nPortefeuille :\n${JSON.stringify(resumePortefeuille(), null, 2)}`,
      }],
      system: 'Tu es un conseiller financier expert des marchés et de la fiscalité française. '
            + 'Réponds en français, de façon structurée et actionnable.',
    });
    sortie.className = 'ia-output';
    sortie.textContent = texteReponse(reponse);
  } catch (e) {
    sortie.className = 'ia-output';
    sortie.textContent = 'Erreur : ' + e.message;
  }
}
