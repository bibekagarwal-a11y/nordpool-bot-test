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
  document.getElementById("table").innerHTML = `
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

function getSelectedValues(id) {
  return [...document.getElementById(id).selectedOptions].map(x => x.value);
}

function selectAll(id) {
  [...document.getElementById(id).options].forEach(o => {
    o.selected = true;
  });
}

function clearAll(id) {
  [...document.getElementById(id).options].forEach(o => {
    o.selected = false;
  });
}

function populateSelectors() {
  const areas = unique(data.map(x => x.area)).filter(Boolean).sort();
  const rules = unique(data.map(x => x.rule)).filter(Boolean).sort();

  if (!areas.length) throw new Error("No areas found in data.");
  if (!rules.length) throw new Error("No rules found in data.");

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
  selectAll("date");
  updateContracts();
}

function updateContracts() {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const selectedDates = getSelectedValues("date");

  const filtered = data
    .filter(d =>
      d.area === area &&
      d.rule === rule &&
      selectedDates.includes(d.date)
    )
    .sort((a, b) => Number(a.contract_sort ?? 0) - Number(b.contract_sort ?? 0));

  const contracts = unique(filtered.map(x => x.contract));
  setOptions("contracts", contracts);
  selectAll("contracts");

  render();
}

function getFilteredRows() {

const area = document.getElementById("area").value;
const rule = document.getElementById("rule").value;
const direction = document.getElementById("direction").value;

const startDate = document.getElementById("startDate").value;
const endDate = document.getElementById("endDate").value;

const selectedContracts = [...document.getElementById("contracts").selectedOptions].map(x => x.value);

let filtered = data.filter(d => {

if (d.area !== area) return false;
if (d.rule !== rule) return false;

if (startDate && d.date < startDate) return false;
if (endDate && d.date > endDate) return false;

if (!selectedContracts.includes(d.contract)) return false;

return true;

}).sort((a,b)=>{
const dateCompare = String(a.date).localeCompare(String(b.date));
if(dateCompare!==0) return dateCompare;
return Number(a.contract_sort ?? 0)-Number(b.contract_sort ?? 0);
});

if(direction==="reverse"){
filtered = filtered.map(d=>({
...d,
buy_price:Number(d.sell_price),
sell_price:Number(d.buy_price),
profit:-Number(d.profit)
}));
}else{
filtered = filtered.map(d=>({
...d,
buy_price:Number(d.buy_price),
sell_price:Number(d.sell_price),
profit:Number(d.profit)
}));
}

return filtered;
} {
  const area = document.getElementById("area").value;
  const rule = document.getElementById("rule").value;
  const direction = document.getElementById("direction").value;
  const selectedDates = getSelectedValues("date");
  const selectedContracts = getSelectedValues("contracts");

  let filtered = data
    .filter(d =>
      d.area === area &&
      d.rule === rule &&
      selectedDates.includes(d.date) &&
      selectedContracts.includes(d.contract)
    )
    .sort((a, b) => {
      const dateCompare = String(a.date).localeCompare(String(b.date));
      if (dateCompare !== 0) return dateCompare;
      return Number(a.contract_sort ?? 0) - Number(b.contract_sort ?? 0);
    });

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

  const profits = filtered.map(x => Number(x.profit));
  const labels = filtered.map(x => `${x.date} | ${x.contract}`);

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
    xaxis: { title: "Profit per contract (€/MWh)", gridcolor: "#eaecf0" },
    yaxis: { title: "Count", gridcolor: "#eaecf0" }
  }, {
    responsive: true,
    displayModeBar: false
  });

  Plotly.newPlot("contractBar", [{
    x: labels,
    y: profits,
    type: "bar",
    marker: { color: "#7c3aed" },
    hovertemplate: "%{x}<br>Profit: %{y:.2f} €/MWh<extra></extra>"
  }], {
    margin: { l: 60, r: 20, t: 20, b: 120 },
    paper_bgcolor: "white",
    plot_bgcolor: "white",
    xaxis: { title: "Date | Contract", tickangle: -60, gridcolor: "#eaecf0" },
    yaxis: { title: "Profit (€/MWh)", gridcolor: "#eaecf0" }
  }, {
    responsive: true,
    displayModeBar: false
  });

  const cumulative = [];
  profits.reduce((acc, val, i) => {
    const next = acc + val;
    cumulative[i] = next;
    return next;
  }, 0);

  Plotly.newPlot("cumulativeCurve", [{
    x: labels,
    y: cumulative,
    mode: "lines+markers",
    line: { color: "#16a34a", width: 3 },
    marker: { size: 6 },
    hovertemplate: "%{x}<br>Cumulative: %{y:.2f} €/MWh<extra></extra>"
  }], {
    margin: { l: 60, r: 20, t: 20, b: 120 },
    paper_bgcolor: "white",
    plot_bgcolor: "white",
    xaxis: { title: "Date | Contract", tickangle: -60, gridcolor: "#eaecf0" },
    yaxis: { title: "Cumulative P&L (€/MWh)", gridcolor: "#eaecf0" }
  }, {
    responsive: true,
    displayModeBar: false
  });

  const top10 = [...filtered]
    .sort((a, b) => b.profit - a.profit)
    .slice(0, 10);

  document.getElementById("topContracts").innerHTML = `
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
        ${top10.map(d => `
          <tr>
            <td>${d.date}</td>
            <td>${d.contract}</td>
            <td>${Number(d.buy_price).toFixed(2)}</td>
            <td>${Number(d.sell_price).toFixed(2)}</td>
            <td>${Number(d.profit).toFixed(2)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  document.getElementById("table").innerHTML = `
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
        ${filtered.map(d => `
          <tr>
            <td>${d.date}</td>
            <td>${d.contract}</td>
            <td>${Number(d.buy_price).toFixed(2)}</td>
            <td>${Number(d.sell_price).toFixed(2)}</td>
            <td>${Number(d.profit).toFixed(2)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

document.getElementById("area").addEventListener("change", updateDates);
document.getElementById("rule").addEventListener("change", updateDates);
document.getElementById("date").addEventListener("change", updateContracts);
document.getElementById("direction").addEventListener("change", render);
document.getElementById("contracts").addEventListener("change", render);

document.getElementById("selectAllDatesBtn").addEventListener("click", () => {
  selectAll("date");
  updateContracts();
});

document.getElementById("clearAllDatesBtn").addEventListener("click", () => {
  clearAll("date");
  render();
});

document.getElementById("selectAllBtn").addEventListener("click", () => {
  selectAll("contracts");
  render();
});

document.getElementById("clearAllBtn").addEventListener("click", () => {
  clearAll("contracts");
  render();
});

loadData();
