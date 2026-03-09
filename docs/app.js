let data = [];

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
  table.innerHTML = `
    <div style="padding:16px;border:1px solid #fda29b;background:#fff1f3;border-radius:12px;color:#b42318;">
      <strong>Data loading error</strong><br />
      ${message}
    </div>
  `;
}

function unique(arr) {
  return [...new Set(arr)];
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

function populateSelectors() {
  const areas = unique(data.map(x => x.area)).filter(Boolean).sort();
  const rules = unique(data.map(x => x.rule)).filter(Boolean).sort();

  if (areas.length === 0) throw new Error("No areas found in data.");
  if (rules.length === 0) throw new Error("No rules found in data.");

  setOptions("area", areas);
  setOptions("rule", rules);

  updateDates();
}

function updateDates() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;

  const filtered = data.filter(d => d.area === area && d.rule === rule);
  const dates = unique(filtered.map(x => x.date)).filter(Boolean).sort();

  setOptions("date", dates);
  updateContracts();
}

function updateContracts() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const date = document.getElementById("date").value;

  const filtered = data
    .filter(d => d.area === area && d.rule === rule && d.date === date)
    .sort((a, b) => Number(a.contract_sort ?? 0) - Number(b.contract_sort ?? 0));

  setOptions("contracts", filtered.map(x => x.contract));

  [...document.getElementById("contracts").options].forEach(o => {
    o.selected = true;
  });

  render();
}

function render() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const date = document.getElementById("date").value;

  const selected = [...document.getElementById("contracts").selectedOptions].map(x => x.value);

  const filtered = data
    .filter(d =>
      d.area === area &&
      d.rule === rule &&
      d.date === date &&
      selected.includes(d.contract)
    )
    .sort((a, b) => Number(a.contract_sort ?? 0) - Number(b.contract_sort ?? 0));

  const profits = filtered.map(x => Number(x.profit));
  const total = profits.reduce((a, b) => a + b, 0);
  const avg = profits.length ? total / profits.length : 0;

  document.getElementById("profit").innerText = `${total.toFixed(2)} €/MWh`;
  document.getElementById("contractCount").innerText = `${filtered.length}`;
  document.getElementById("avgProfit").innerText = `${avg.toFixed(2)} €/MWh`;

  Plotly.newPlot("histogram", [{
    x: profits,
    type: "histogram",
    marker: { color: "#2563eb" },
    hovertemplate: "Profit: %{x:.2f} €/MWh<br>Count: %{y}<extra></extra>"
  }], {
    margin: { l: 60, r: 20, t: 20, b: 60 },
    paper_bgcolor: "white",
    plot_bgcolor: "white",
    xaxis: {
      title: "Profit per contract (€/MWh)",
      gridcolor: "#eaecf0",
      zerolinecolor: "#d0d5dd"
    },
    yaxis: {
      title: "Count",
      gridcolor: "#eaecf0"
    }
  }, {
    responsive: true,
    displayModeBar: false
  });

  const rows = filtered.map(d => `
    <tr>
      <td>${d.contract}</td>
      <td>${Number(d.buy_price).toFixed(2)}</td>
      <td>${Number(d.sell_price).toFixed(2)}</td>
      <td>${Number(d.profit).toFixed(2)}</td>
    </tr>
  `).join("");

  document.getElementById("table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Contract</th>
          <th>Buy</th>
          <th>Sell</th>
          <th>Profit</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

document.getElementById("area").addEventListener("change", updateDates);
document.getElementById("rule").addEventListener("change", updateDates);
document.getElementById("date").addEventListener("change", updateContracts);
document.getElementById("contracts").addEventListener("change", render);

document.getElementById("selectAllBtn").addEventListener("click", () => {
  [...document.getElementById("contracts").options].forEach(o => {
    o.selected = true;
  });
  render();
});

document.getElementById("clearAllBtn").addEventListener("click", () => {
  [...document.getElementById("contracts").options].forEach(o => {
    o.selected = false;
  });
  render();
});

loadData();
