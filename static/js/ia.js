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
  return {
    totalPatrimoine: totalPortefeuille().toFixed(2),
    comptes: comptes().map(c => ({
      nom: c.nom,
      enveloppe: typeInfo(c.type).nom_complet || typeInfo(c.type).label,
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
      max_tokens: 1500,
      messages: [{
        role: 'user',
        content: `${PROMPTS[mode]}\n\nPortefeuille :\n${JSON.stringify(resumePortefeuille(), null, 2)}`,
      }],
      system: 'Tu es un conseiller financier expert des marchés et de la fiscalité française. '
            + 'Réponds en français, de façon structurée et actionnable.',
    });
    sortie.className = 'ia-output';
    sortie.textContent = reponse.content?.map(bloc => bloc.text || '').join('') || reponse.error || 'Réponse vide.';
  } catch (e) {
    sortie.className = 'ia-output';
    sortie.textContent = 'Erreur : ' + e.message;
  }
}
