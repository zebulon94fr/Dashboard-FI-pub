import { Store } from './state.js';
import { render } from './core.js';

export function cssVar(nom) {
  return getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
}

export function chartColors() {
  return { muted: cssVar('--muted'), grid: cssVar('--border') + '66' };
}

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('btnTheme').textContent = theme === 'light' ? '☀️' : '🌙';
  if (Store.DATA?.accounts?.length) render();
}

export function toggleTheme() {
  const actuel = document.documentElement.getAttribute('data-theme') || 'dark';
  const suivant = actuel === 'dark' ? 'light' : 'dark';
  localStorage.setItem('dashboardfi_theme', suivant);
  applyTheme(suivant);
}

export function initTheme() {
  const sauvegarde = localStorage.getItem('dashboardfi_theme');
  const theme = sauvegarde || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('btnTheme');
  if (btn) btn.textContent = theme === 'light' ? '☀️' : '🌙';
}
