let bessSummary = [];
let bessTrades = [];
let bessSchedule = [];

async function loadBessData() {
  try {
    const [summaryRes, tradesRes, scheduleRes] = await Promise.all([
      fetch("./data/bess_summary.json", { cache: "no-store" }),
      fetch("./data/bess_trades.json", { cache: "no-store" }),
      fetch("./data/bess_schedule.json", { cache: "no-store" }),
    ]);

    bessSummary = await summaryRes.json();
    bessTrades = await tradesRes.json();
    bessSchedule = await scheduleRes.json();

    initSelectors();
  } catch (err) {
    console.error("Error loading BESS data:", err);
  }
}

function unique(arr) {
  return [...new Set(arr)].sort();
}

function setOptions(id, values) {
  const el = document.getElementById(id);
  if (!el) return;
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
  const totalPnlEl = document.getElementById("bessTotalPnl");
  if (totalPnlEl) {
    totalPnlEl.innerText = totalRow ? `${Number(totalRow.stage_pnl_eur).toFixed(2)} €` : "-";
  }

  const stageRows = summary.filter(x => x.stage !== "TOTAL");
  
  const waterfallTrace = {
    x: stageRows.map(x => x.stage),
    y: stageRows.map(x => Number(x.stage_pnl_eur)),
    type: "bar",
    marker: { color: "#2563eb" }
  };

  const waterfallLayout = {
    margin: { t: 20, b: 60, l: 60, r: 20 },
    xaxis: { title: "Strategy Stage" },
    yaxis: { title: "PnL (€)" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("bessWaterfall", [waterfallTrace], waterfallLayout, { responsive: true, displayModeBar: false });

  const socTrace = {
    x: schedule.map(x => x.contract),
    y: schedule.map(x => Number(x.soc_mwh)),
    type: "scatter",
    mode: "lines",
    name: "SOC (MWh)",
    line: { color: "#16a34a", width: 3 },
    fill: "tozeroy",
    fillcolor: "rgba(22, 163, 74, 0.1)"
  };

  const socLayout = {
    margin: { t: 20, b: 80, l: 60, r: 20 },
    xaxis: { title: "Contract" },
    yaxis: { title: "SOC (MWh)" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("bessSocChart", [socTrace], socLayout, { responsive: true, displayModeBar: false });

  renderTradeTable(trades);
}

function renderTradeTable(trades) {
  const el = document.getElementById("bessTradeTable");
  if (!el) return;

  if (trades.length === 0) {
    el.innerHTML = "<p>No trades for this selection</p>";
    return;
  }

  let html = `
    <table>
      <thead>
        <tr>
          <th>Contract</th>
          <th>Side</th>
          <th>Price</th>
          <th>Volume</th>
          <th>PnL</th>
        </tr>
      </thead>
      <tbody>
  `;

  trades.forEach(t => {
    const pnl = Number(t.pnl_eur);
    const pnlClass = pnl >= 0 ? "profit-pos" : "profit-neg";
    html += `
      <tr>
        <td>${t.contract}</td>
        <td>${t.side}</td>
        <td>${Number(t.price_eur).toFixed(2)}</td>
        <td>${Number(t.volume_mwh).toFixed(3)}</td>
        <td class="${pnlClass}">${pnl.toFixed(2)}</td>
      </tr>
    `;
  });

  html += "</tbody></table>";
  el.innerHTML = html;
}

const areaEl = document.getElementById("bessArea");
if (areaEl) areaEl.addEventListener("change", updateDateSelector);

const dateEl = document.getElementById("bessDate");
if (dateEl) dateEl.addEventListener("change", renderBess);

loadBessData();
