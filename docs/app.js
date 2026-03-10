let data = [];

const RULE_LABELS = {
  DA_IDA1: "Day Ahead ↔ IDA1",
  DA_IDA2: "Day Ahead ↔ IDA2",
  DA_IDA3: "Day Ahead ↔ IDA3",
  DA_VWAP: "Day Ahead ↔ Intraday VWAP",
  IDA1_IDA2: "IDA1 ↔ IDA2",
  IDA1_IDA3: "IDA1 ↔ IDA3",
  IDA1_VWAP: "IDA1 ↔ Intraday VWAP",
  IDA2_IDA3: "IDA2 ↔ IDA3",
  IDA2_VWAP: "IDA2 ↔ Intraday VWAP",
  IDA3_VWAP: "IDA3 ↔ Intraday VWAP"
};

async function loadData() {
  try {
    const res = await fetch("./data/contract_profits.json", { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`Failed to load data: ${res.status} ${res.statusText}`);
    }

    data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
      throw new Error("contract_profits.json loaded, but it is empty.");
    }

    populateSelectors();
  } catch (err) {
    console.error(err);
    showError(err.message);
  }
}

function showError(message) {
  const table = document.getElementById("table");
  if (table) {
    table.innerHTML = `
      <div style="padding:16px;border:1px solid #fda29b;background:#fff1f3;border-radius:12px;color:#b42318;">
        <strong>Data loading error</strong><br />
        ${message}
      </div>
    `;
  }
}

function unique(arr) {
  return [...new Set(arr)];
}

function setOptions(id, values, labelMap = null) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = "";

  values.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.text = labelMap && labelMap[v] ? labelMap[v] : v;
    el.appendChild(opt);
  });
}

function selectAllOptions(id) {
  const el = document.getElementById(id);
  if (!el) return;
  [...el.options].forEach(o => {
    o.selected = true;
  });
}

function clearAllOptions(id) {
  const el = document.getElementById(id);
  if (!el) return;
  [...el.options].forEach(o => {
    o.selected = false;
  });
}

function getSelectedValues(id) {
  const el = document.getElementById(id);
  if (!el) return [];
  return [...el.options].filter(o => o.selected).map(o => o.value);
}

function populateSelectors() {
  const areas = unique(data.map(x => x.area)).filter(Boolean).sort();
  const rules = unique(data.map(x => x.rule)).filter(Boolean).sort();
  const dates = unique(data.map(x => x.date)).filter(Boolean).sort();

  if (!areas.length) throw new Error("No areas found in data.");
  if (!rules.length) throw new Error("No strategies found in data.");
  if (!dates.length) throw new Error("No dates found in data.");

  setOptions("area", areas);
  setOptions("rule", rules, RULE_LABELS);

  document.getElementById("startDate").value = dates[0];
  document.getElementById("endDate").value = dates[dates.length - 1];

  updateContracts();
}

function updateContracts() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const startDate = document.getElementById("startDate").value;
  const endDate = document.getElementById("endDate").value;

  const filtered = data
    .filter(d => {
      if (d.area !== area) return false;
      if (d.rule !== rule) return false;
      if (startDate && d.date < startDate) return false;
      if (endDate && d.date > endDate) return false;
      return true;
    })
    .sort(compareRowsChronologically);

  // Use contract_sort to ensure chronological ordering of contract names
  const contracts = unique(filtered.sort((a, b) => a.contract_sort - b.contract_sort).map(x => x.contract));
  setOptions("contracts", contracts);
  selectAllOptions("contracts");
  setActivePreset("presetBaseBtn");

  render();
}

function compareRowsChronologically(a, b) {
  if (a.date < b.date) return -1;
  if (a.date > b.date) return 1;
  return a.contract_sort - b.contract_sort;
}

function getFilteredRows() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const direction = document.getElementById("direction").value;
  const startDate = document.getElementById("startDate").value;
  const endDate = document.getElementById("endDate").value;
  const selectedContracts = getSelectedValues("contracts");

  let filtered = data
    .filter(d => {
      if (d.area !== area) return false;
      if (d.rule !== rule) return false;
      if (startDate && d.date < startDate) return false;
      if (endDate && d.date > endDate) return false;
      if (!selectedContracts.includes(d.contract)) return false;
      return true;
    })
    .sort(compareRowsChronologically);

  if (direction === "reverse") {
    filtered = filtered.map(d => ({
      ...d,
      buy_price: Number(d.sell_price),
      sell_price: Number(d.buy_price),
      profit: -Number(d.profit)
    }));
  } else {
    filtered = filtered.map(d => ({
      ...d,
      buy_price: Number(d.buy_price),
      sell_price: Number(d.sell_price),
      profit: Number(d.profit)
    }));
  }

  return filtered;
}

function render() {
  const filtered = getFilteredRows();

  renderMetricCards(filtered);
  renderBessStrategy(filtered);
  renderMultiCycleBess(filtered);
  renderCumulativeCurve(filtered);
  renderContractBar(filtered);
  renderHeatmap(filtered);
  renderHistogram(filtered);
  renderTopBottomTables(filtered);
  renderBreakdownTable(filtered);
}

function renderMetricCards(rows) {
  const total = rows.reduce((acc, r) => acc + r.profit, 0);
  const count = rows.length;
  const avg = count > 0 ? total / count : 0;
  const wins = rows.filter(r => r.profit > 0).length;
  const winRate = count > 0 ? (wins / count) * 100 : 0;

  document.getElementById("totalProfit").innerText = `${total.toFixed(2)} €/MWh`;
  document.getElementById("rowCount").innerText = count;
  document.getElementById("avgProfit").innerText = `${avg.toFixed(2)} €/MWh`;
  document.getElementById("winRate").innerText = `${winRate.toFixed(1)}%`;

  if (count > 0) {
    const sorted = [...rows].sort((a, b) => b.profit - a.profit);
    const best = sorted[0];
    const worst = sorted[sorted.length - 1];

    document.getElementById("bestRow").innerHTML = `
      <div style="font-size:14px; color:#667085;">${best.date}</div>
      <div style="font-size:14px; color:#667085;">${best.contract}</div>
      <div style="color:#16a34a; font-weight:700;">${best.profit.toFixed(2)} €/MWh</div>
    `;
    document.getElementById("worstRow").innerHTML = `
      <div style="font-size:14px; color:#667085;">${worst.date}</div>
      <div style="font-size:14px; color:#667085;">${worst.contract}</div>
      <div style="color:#dc2626; font-weight:700;">${worst.profit.toFixed(2)} €/MWh</div>
    `;
  } else {
    document.getElementById("bestRow").innerText = "-";
    document.getElementById("worstRow").innerText = "-";
  }
}

function renderBessStrategy(rows) {
  const el = document.getElementById("bestBessResult");
  if (rows.length < 2) {
    el.innerText = "Need at least 2 rows for BESS";
    return;
  }

  const buys = [...rows].sort((a, b) => a.buy_price - b.buy_price);
  const sells = [...rows].sort((a, b) => b.sell_price - a.sell_price);

  const bestBuy = buys[0];
  const bestSell = sells[0];
  const spread = bestSell.sell_price - bestBuy.buy_price;

  el.innerHTML = `
    <strong>Charge:</strong> ${bestBuy.date} | ${bestBuy.contract} at ${bestBuy.buy_price.toFixed(2)} €/MWh <br />
    <strong>Discharge:</strong> ${bestSell.date} | ${bestSell.contract} at ${bestSell.sell_price.toFixed(2)} €/MWh <br />
    <strong>Single-cycle spread:</strong> ${spread.toFixed(2)} €/MWh
  `;
}

function renderMultiCycleBess(rows) {
  const dates = unique(rows.map(r => r.date)).sort();
  const dailyPnL = dates.map(d => {
    const dayRows = rows.filter(r => r.date === d);
    if (dayRows.length === 0) return 0;
    const sortedBuys = [...dayRows].sort((a, b) => a.buy_price - b.buy_price);
    const sortedSells = [...dayRows].sort((a, b) => b.sell_price - a.sell_price);
    return sortedSells[0].sell_price - sortedBuys[0].buy_price;
  });

  const trace = {
    x: dates,
    y: dailyPnL,
    type: "bar",
    marker: { color: "#2563eb" },
    name: "Daily Spread"
  };

  const layout = {
    margin: { t: 20, b: 40, l: 60, r: 20 },
    xaxis: { title: "Date" },
    yaxis: { title: "Max Spread (€/MWh)" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("bessMultiChart", [trace], layout, { responsive: true, displayModeBar: false });
}

function renderCumulativeCurve(rows) {
  let sum = 0;
  const x = [];
  const y = [];

  rows.forEach(r => {
    sum += r.profit;
    x.push(`${r.date} | ${r.contract}`);
    y.push(sum);
  });

  const trace = {
    x: x,
    y: y,
    type: "scatter",
    mode: "lines",
    line: { color: "#2563eb", width: 3 },
    fill: "tozeroy",
    fillcolor: "rgba(37, 99, 235, 0.1)"
  };

  const layout = {
    margin: { t: 20, b: 80, l: 60, r: 20 },
    xaxis: { showticklabels: false, title: "Date | Contract" },
    yaxis: { title: "Cumulative P&L (€/MWh)" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("cumulativeChart", [trace], layout, { responsive: true, displayModeBar: false });
}

function renderContractBar(rows) {
  const trace = {
    x: rows.map(r => `${r.date} | ${r.contract}`),
    y: rows.map(r => r.profit),
    type: "bar",
    marker: {
      color: rows.map(r => (r.profit >= 0 ? "#16a34a" : "#dc2626"))
    }
  };

  const layout = {
    margin: { t: 20, b: 80, l: 60, r: 20 },
    xaxis: { showticklabels: false, title: "Date | Contract" },
    yaxis: { title: "Profit (€/MWh)" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("contractBarChart", [trace], layout, { responsive: true, displayModeBar: false });
}

function renderHeatmap(rows) {
  const dates = unique(rows.map(r => r.date)).sort();
  const contracts = unique(rows.sort((a, b) => a.contract_sort - b.contract_sort).map(r => r.contract));

  const z = contracts.map(c => {
    return dates.map(d => {
      const match = rows.find(r => r.date === d && r.contract === c);
      return match ? match.profit : null;
    });
  });

  const trace = {
    x: dates,
    y: contracts,
    z: z,
    type: "heatmap",
    colorscale: [
      [0, "#dc2626"],
      [0.5, "#f8fafc"],
      [1, "#16a34a"]
    ],
    zmid: 0
  };

  const layout = {
    margin: { t: 20, b: 40, l: 100, r: 20 },
    xaxis: { title: "Date" },
    yaxis: { title: "Quarter-hour contract", autorange: "reversed" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("heatmapChart", [trace], layout, { responsive: true, displayModeBar: false });
}

function renderHistogram(rows) {
  const trace = {
    x: rows.map(r => r.profit),
    type: "histogram",
    marker: { color: "#2563eb", line: { color: "white", width: 1 } },
    nbinsx: 30
  };

  const layout = {
    margin: { t: 20, b: 40, l: 60, r: 20 },
    xaxis: { title: "Profit per row (€/MWh)" },
    yaxis: { title: "Count" },
    font: { family: "Inter" }
  };

  Plotly.newPlot("histogramChart", [trace], layout, { responsive: true, displayModeBar: false });
}

function renderTopBottomTables(rows) {
  const sorted = [...rows].sort((a, b) => b.profit - a.profit);
  const top = sorted.slice(0, 10);
  const bottom = [...sorted].reverse().slice(0, 10);

  document.getElementById("topTable").innerHTML = createTableHtml(top);
  document.getElementById("bottomTable").innerHTML = createTableHtml(bottom);
}

function renderBreakdownTable(rows) {
  document.getElementById("table").innerHTML = createTableHtml(rows);
}

function createTableHtml(rows) {
  if (rows.length === 0) return "<p>No data</p>";

  let html = `
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Contract</th>
          <th>Buy</th>
          <th>Sell</th>
          <th>Profit</th>
        </tr>
      </thead>
      <tbody>
  `;

  rows.forEach(r => {
    const profitClass = r.profit >= 0 ? "profit-pos" : "profit-neg";
    html += `
      <tr>
        <td>${r.date}</td>
        <td>${r.contract}</td>
        <td>${r.buy_price.toFixed(2)}</td>
        <td>${r.sell_price.toFixed(2)}</td>
        <td class="${profitClass}">${r.profit.toFixed(2)}</td>
      </tr>
    `;
  });

  html += "</tbody></table>";
  return html;
}

function setActivePreset(id) {
  const btns = document.querySelectorAll(".contract-presets button");
  btns.forEach(b => b.classList.remove("active"));
  if (id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("active");
  }
}

function applyContractPreset(type) {
  const el = document.getElementById("contracts");
  if (!el) return;

  clearAllOptions("contracts");

  const options = [...el.options];

  options.forEach(opt => {
    const val = opt.value;
    const hour = parseInt(val.split(":")[0]);

    if (type === "base") {
      opt.selected = true;
    } else if (type === "peak") {
      if (hour >= 8 && hour < 20) opt.selected = true;
    } else if (type === "offpeak") {
      if (hour < 8 || hour >= 20) opt.selected = true;
    } else if (type === "morning") {
      if (hour >= 6 && hour < 10) opt.selected = true;
    } else if (type === "evening") {
      if (hour >= 17 && hour < 21) opt.selected = true;
    }
  });

  setActivePreset(`preset${type.charAt(0).toUpperCase() + type.slice(1)}Btn`);
  render();
}

document.getElementById("area").addEventListener("change", updateContracts);
document.getElementById("rule").addEventListener("change", updateContracts);
document.getElementById("direction").addEventListener("change", render);
document.getElementById("startDate").addEventListener("change", updateContracts);
document.getElementById("endDate").addEventListener("change", updateContracts);

document.getElementById("contracts").addEventListener("change", () => {
  setActivePreset(null);
  render();
});

document.getElementById("selectAllBtn").addEventListener("click", () => {
  selectAllOptions("contracts");
  setActivePreset("presetBaseBtn");
  render();
});

document.getElementById("clearAllBtn").addEventListener("click", () => {
  clearAllOptions("contracts");
  setActivePreset(null);
  render();
});

document.getElementById("presetBaseBtn").addEventListener("click", () => {
  applyContractPreset("base");
});

document.getElementById("presetPeakBtn").addEventListener("click", () => {
  applyContractPreset("peak");
});

document.getElementById("presetOffPeakBtn").addEventListener("click", () => {
  applyContractPreset("offpeak");
});

document.getElementById("presetMorningBtn").addEventListener("click", () => {
  applyContractPreset("morning");
});

document.getElementById("presetEveningBtn").addEventListener("click", () => {
  applyContractPreset("evening");
});

loadData();
