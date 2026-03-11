let allData = [];
let filteredData = [];
let selectors = {};

document.addEventListener("DOMContentLoaded", () => {
  loadData();
});

async function loadData() {

  try {

    const dataResponse = await fetch("data/contract_profits.json");
    allData = await dataResponse.json();
    filteredData = [...allData];

    const selectorResponse = await fetch("data/selector_options.json");
    selectors = await selectorResponse.json();

    populateSelectors();
    renderChart();

    document.getElementById("area").addEventListener("change", applyFilters);
    document.getElementById("strategy").addEventListener("change", applyFilters);
    document.getElementById("contract").addEventListener("change", applyFilters);

  } catch(err) {
    console.error("Error loading data:", err);
  }

}

function populateSelectors(){

  const areaSelect = document.getElementById("area");
  const strategySelect = document.getElementById("strategy");
  const contractSelect = document.getElementById("contract");

  selectors.areas.forEach(a=>{
    const opt=document.createElement("option");
    opt.value=a;
    opt.textContent=a;
    areaSelect.appendChild(opt);
  });

  selectors.rules.forEach(r=>{
    const opt=document.createElement("option");
    opt.value=r;
    opt.textContent=r;
    strategySelect.appendChild(opt);
  });

  selectors.contracts.forEach(c=>{
    const opt=document.createElement("option");
    opt.value=c;
    opt.textContent=c;
    contractSelect.appendChild(opt);
  });

}

function applyFilters(){

  const area=document.getElementById("area").value;
  const strategy=document.getElementById("strategy").value;
  const contract=document.getElementById("contract").value;

  filteredData=allData.filter(d=>{
    const areaMatch=!area||d.area===area;
    const stratMatch=!strategy||d.rule===strategy;
    const contractMatch=!contract||d.contract===contract;

    return areaMatch && stratMatch && contractMatch;
  });

  renderChart();

}

function renderChart(){

  if(filteredData.length === 0){
    Plotly.purge("cumulativePLChart");
    return;
  }

  let cumulative = 0;

  const x = [];
  const y = [];

  filteredData
    .sort((a,b)=>a.contract_sort - b.contract_sort)
    .forEach(r=>{
      cumulative += parseFloat(r.profit) || 0;

      // combine date and contract time for X axis
      x.push(`${r.date} ${r.contract}`);

      y.push(cumulative);
    });

  Plotly.newPlot("cumulativePLChart",[{
    x: x,
    y: y,
    type: "scatter",
    mode: "lines",
    line: { color:"#4ade80" }
  }]);

}
