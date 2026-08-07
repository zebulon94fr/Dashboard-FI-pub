// Couleurs dérivées du type d'enveloppe : deux comptes de même type restent
// reconnaissables sans sortir de la palette.
import { typeInfo } from './state.js';

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Éclaircit (`ratio` > 0) ou assombrit (`ratio` < 0) une couleur hexadécimale.
 *  Renvoie du #rrggbb pour rester composable (suffixe d'opacité, alpha()…). */
export function shade(hex, ratio) {
  const cible = ratio > 0 ? 255 : 0;
  const k = Math.abs(ratio);
  return '#' + hexToRgb(hex)
    .map(v => Math.round(v + (cible - v) * k).toString(16).padStart(2, '0'))
    .join('');
}

export function alpha(hex, a) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}

/**
 * Une couleur par compte : celle de son type, nuancée quand plusieurs comptes
 * partagent le même type.
 */
export function couleursComptes(comptes) {
  const rangs = {};
  return comptes.map(c => {
    const base = typeInfo(c.type).couleur || '#8b949e';
    const rang = rangs[c.type] = (rangs[c.type] ?? -1) + 1;
    return rang === 0 ? base : shade(base, rang % 2 ? 0.28 * Math.ceil(rang / 2) : -0.22 * (rang / 2));
  });
}

// Palette de repli pour les regroupements libres (secteurs, zones géographiques).
export const PALETTE = [
  '#58a6ff', '#3fb950', '#bc8cff', '#f0883e', '#f5c518', '#39d353',
  '#79c0ff', '#d2a8ff', '#e3b341', '#56d364', '#1f6feb', '#a371f7',
];

export const couleurIndex = i => PALETTE[i % PALETTE.length];
