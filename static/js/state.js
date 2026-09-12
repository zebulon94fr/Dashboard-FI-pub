// État partagé entre les modules. Les modules mutent les propriétés de cet objet
// plutôt que de réassigner des variables globales (contrainte des modules ES).
export const Store = {
  DATA: { accounts: [], history: [], lastUpdate: '' },
  STATS: null,      // dernier /api/stats — null tant qu'il n'a pas répondu
  TYPES: {},        // catalogue des types d'enveloppes, indexé par id
  TYPES_LIST: [],   // même catalogue, dans l'ordre d'affichage
  DEVISES: ['EUR'],
  dividendes: [],   // dernier chargement de /api/dividendes (édition en place)
  charts: {},
  amountsHidden: false,
  currentAccountId: null,   // compte affiché dans la section « compte »
};

const TYPE_INCONNU = {
  id: '', label: '—', icone: '•', couleur: '#8b949e',
  unite: 'unités', decimales: 4, devise_defaut: 'EUR',
  regles: [], suggestions: [], resume_fiscal: '', modele_fiscal: 'flat',
};

export const typeInfo = id => Store.TYPES[id] || TYPE_INCONNU;

export const comptes = () => Store.DATA.accounts || [];

export const compteById = id => comptes().find(c => c.id === Number(id)) || null;

/** Toutes les positions du portefeuille, chacune enrichie de son compte (`_compte`). */
export const toutesPositions = () =>
  comptes().flatMap(c => (c.positions || []).map(p => ({ ...p, _compte: c })));

export const totalPortefeuille = () =>
  comptes().reduce((s, c) => s + (c.valorisation || 0), 0);

export const investiPortefeuille = () =>
  comptes().reduce((s, c) => s + (c.investi || 0), 0);
