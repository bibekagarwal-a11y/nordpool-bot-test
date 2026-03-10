let bessSummary = [];
let bessTrades = [];
let bessSchedule = [];

async function loadBessData() {
  const [summaryRes, tradesRes, scheduleRes] = await Promise.all([
    fetch("./data/bess_summary.json", { cache: "no-store" }),
    fetch("./data/bess_trades.json", { cache: "no-store" }),
    fetch("./data/bess_schedule.json", { cache: "no-store" }),
  ]);

  bessSummary = await summaryRes.json();
  bessTrades = await tradesRes.json();
  bessSchedule = await scheduleRes.json();

  initSelectors();
}

function unique(arr) {
  return [...new Set(arr)].sort();
}

function setOptions(id, values) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  values.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.text = v;
    el.appendChild(opt);
  });
}

function initSelectors() {
  const areas = unique(bessSummary.map(x => x.area).filter(Boolean));
  setOptions("bessArea", areas);
  updateDateSelector();
}

function updateDateSelector() {
  const area = document.getElementById("bessArea").value;
  const dates = unique(bessSummary.filter(x => x.area === area).map(x => x.date).filter(Boolean));
  setOptions("bessDate", dates);
  renderBess();
}

function renderBess() {
  const area = document.getElementById("bessArea").value;
  const date = document.getElementById("bessDate").value;

  const summary = bessSummary.filter(x => x.area === area && x.date === date);
  const trades = bessTrades.filter(x => x.area === area && x.date === date);
  const schedule = bessSchedule.filter(x => x.area === area && x.date === date);

  const totalRow = summary.find(x => x.stage === "TOTAL");
  document.getElementById("bessTotalPnl").innerText =
    totalRow ? `${Number(totalRow.stage_pnl_eur).toFixed(2)} €` : "-";

  const stageRows = summary.filter(x => x.stage !== "TOTAL");
  Plotly.newPlot("bessWaterfall", [{
    x: stageRows.map(x => x.stage),
    y: stageRows.map(x => Number(x.stage_pnl_eur)),
    type: "bar"
  }], {
    margin: { l: 60, r: 20, t: 20, b: 60 }
  }, {
    responsive: true,
    displayModeBar: false
  });

  const schedSorted = [...schedule].sort((a, b) => Number(a.contract_sort) - Number(b.contract_sort));
  Plotly.newPlot("bessSocChart", [{
    x: schedSorted.map(x => `${x.stage} | ${x.contract}`),
    y: schedSorted.map(x => Number(x.soc_mwh)),
    mode: "lines+markers",
    name: "SOC"
  }], {
    margin: { l: 60, r: 20, t: 20, b: 100 }
  }, {
    responsive: true,
    displayModeBar: false
  });

  document.getElementById("bessTradeTable").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Stage</th>
          <th>Contract</th>
          <th>Side</th>
          <th>Energy MWh</th>
          <th>Price</th>
          <th>Cashflow €</th>
        </tr>
      </thead>
      <tbody>
        ${trades.map(t => `
          <tr>
            <td>${t.stage}</td>
            <td>${t.contract}</td>
            <td>${t.side}</td>
            <td>${Number(t.energy_mwh).toFixed(3)}</td>
            <td>${Number(t.price_eur_mwh).toFixed(2)}</td>
            <td>${Number(t.cashflow_eur).toFixed(2)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

document.getElementById("bessArea").addEventListener("change", updateDateSelector);
document.getElementById("bessDate").addEventListener("change", renderBess);

loadBessData();
