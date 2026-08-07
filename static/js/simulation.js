import { totalPortefeuille, investiPortefeuille } from './state.js';
import { fmt, fmtN, fmtP, cls, kpiCard, makeChart } from './core.js';
import { chartColors } from './theme.js';

export function setSimReturn(valeur) {
  document.getElementById('simReturn').value = valeur;
  document.querySelectorAll('.sim-preset').forEach(b => {
    const v = parseFloat(b.textContent.match(/[\d.]+/)?.[0]);
    b.classList.toggle('active', v === valeur);
  });
  simUpdate();
}

export function getSimBase() {
  const base = document.querySelector('input[name=simBase]:checked')?.value || 'current';
  if (base === 'custom') return parseFloat(document.getElementById('simCustomStart').value) || 0;
  return base === 'current' ? totalPortefeuille() : investiPortefeuille();
}

export function projectGrowth(depart, tauxAnnuel, mensuel, annees) {
  const tauxMensuel = Math.pow(1 + tauxAnnuel / 100, 1 / 12) - 1;
  const points = [depart];
  let valeur = depart;
  for (let m = 1; m <= annees * 12; m++) {
    valeur = (valeur + mensuel) * (1 + tauxMensuel);
    if (m % 12 === 0) points.push(valeur);
  }
  return points;
}

export function simUpdate() {
  const annees   = parseInt(document.getElementById('simYears').value) || 20;
  const taux     = parseFloat(document.getElementById('simReturn').value) || 7;
  const mensuel  = parseFloat(document.getElementById('simMonthly').value) || 0;
  const inflation = parseFloat(document.getElementById('simInflation').value) || 2;
  const bear = document.getElementById('simBear').checked;
  const bull = document.getElementById('simBull').checked;
  const reel = document.getElementById('simReal').checked;
  const depart = getSimBase();

  document.getElementById('simYearsVal').textContent     = annees + ' an' + (annees > 1 ? 's' : '');
  document.getElementById('simReturnVal').textContent    = taux.toFixed(1).replace('.', ',') + ' %/an';
  document.getElementById('simMonthlyVal').textContent   = mensuel.toLocaleString('fr-FR') + ' €/mois';
  document.getElementById('simInflationVal').textContent = inflation.toFixed(1).replace('.', ',') + ' %/an';

  const labels = Array.from({ length: annees + 1 }, (_, i) =>
    i === 0 ? 'Auj.' : String(new Date().getFullYear() + i));

  const central = projectGrowth(depart, taux, mensuel, annees);
  const pessimiste = bear ? projectGrowth(depart, Math.max(0, taux - 3), mensuel, annees) : null;
  const optimiste  = bull ? projectGrowth(depart, taux + 3, mensuel, annees) : null;
  const pouvoirAchat = reel ? central.map((v, i) => v / Math.pow(1 + inflation / 100, i)) : null;

  const datasets = [{
    label: `Scénario central (${taux.toFixed(1)} %)`, data: central,
    borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.08)',
    fill: true, tension: .4, pointRadius: 2, pointHoverRadius: 5, borderWidth: 2.5, order: 1,
  }];
  if (pessimiste) datasets.push({ label: `Pessimiste (${(taux - 3).toFixed(1)} %)`, data: pessimiste, borderColor: '#f85149', backgroundColor: 'transparent', fill: false, tension: .4, pointRadius: 0, pointHoverRadius: 5, borderWidth: 1.5, borderDash: [5, 5], order: 2 });
  if (optimiste)  datasets.push({ label: `Optimiste (${(taux + 3).toFixed(1)} %)`, data: optimiste, borderColor: '#3fb950', backgroundColor: 'transparent', fill: false, tension: .4, pointRadius: 0, pointHoverRadius: 5, borderWidth: 1.5, borderDash: [5, 5], order: 3 });
  if (pouvoirAchat) datasets.push({ label: `Réel (inflation ${inflation.toFixed(1)} %)`, data: pouvoirAchat, borderColor: '#d29922', backgroundColor: 'transparent', fill: false, tension: .4, pointRadius: 0, pointHoverRadius: 5, borderWidth: 1.5, borderDash: [3, 4], order: 4 });

  makeChart('chartSim', {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { color: chartColors().muted, boxWidth: 14, usePointStyle: true, pointStyle: 'line' } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label} : ${fmtN(ctx.raw)} €` } },
      },
      scales: {
        x: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, maxTicksLimit: 10 } },
        y: { grid: { color: chartColors().grid }, ticks: { color: chartColors().muted, callback: v => v >= 1e6 ? +(v / 1e6).toFixed(2) + 'M €' : fmtN(v) + '€' } },
      },
    },
  });

  const valeurFinale = central[central.length - 1];
  const investi = depart + mensuel * 12 * annees;
  const gains = valeurFinale - investi;
  const gainPct = investi > 0 ? gains / investi : 0;

  document.getElementById('simCards').innerHTML =
    kpiCard('Valeur finale estimée', fmt(valeurFinale), `Scénario central ${taux.toFixed(1)} %`, 'neu') +
    kpiCard('Capital investi', fmt(investi), mensuel > 0 ? `${mensuel.toLocaleString('fr-FR')} €/mois` : 'Sans versement', 'neu') +
    kpiCard('Gains générés', fmt(gains), fmtP(gainPct), cls(gains)) +
    (pouvoirAchat ? kpiCard('Valeur réelle', fmt(pouvoirAchat[pouvoirAchat.length - 1]), `Hors inflation ${inflation.toFixed(1)} %`, 'neu') : '') +
    (pessimiste ? kpiCard('Scénario pessimiste', fmt(pessimiste[pessimiste.length - 1]), `${(taux - 3).toFixed(1)} %/an`, 'neg') : '') +
    (optimiste ? kpiCard('Scénario optimiste', fmt(optimiste[optimiste.length - 1]), `+${(taux + 3).toFixed(1)} %/an`, 'pos') : '');

  const lignes = central.map((v, i) => {
    if (i === 0) return `<tr><td class="muted">Aujourd'hui</td><td>${new Date().getFullYear()}</td><td>${fmt(v)}</td><td>—</td><td>—</td><td>—</td></tr>`;
    const gainAnnuel = v - central[i - 1] - mensuel * 12;
    const investiCumule = depart + mensuel * 12 * i;
    const pv = v - investiCumule;
    return `<tr>
      <td>Année ${i}</td>
      <td>${new Date().getFullYear() + i}</td>
      <td>${fmt(v)}</td>
      <td class="${cls(gainAnnuel)}">${fmt(gainAnnuel)}</td>
      <td class="${cls(pv)}">${fmt(pv)} <span style="font-size:10px">(${fmtP(investiCumule > 0 ? pv / investiCumule : 0)})</span></td>
      <td>${pouvoirAchat ? fmt(pouvoirAchat[i]) : '—'}</td>
    </tr>`;
  }).join('');

  document.getElementById('simTable').innerHTML =
    `<thead><tr><th>Période</th><th>Année</th><th>Valorisation</th><th>Gain annuel</th><th>Plus-value cumulée</th><th>Valeur réelle</th></tr></thead>
     <tbody>${lignes}</tbody>`;
}
