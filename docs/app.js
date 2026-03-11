function renderChart(){

  let filteredData = [];
let allData = [];

async function loadData(){

  try{

    const res = await fetch("./reports/arbitrage_opportunities_all_areas.csv");

    if(!res.ok){
      throw new Error("Dataset not found");
    }

    const text = await res.text();

    const rows = text.split("\n").slice(1);

    allData = rows
      .map(r => r.split(","))
      .filter(r => r.length > 5)
      .map(r => ({
        date: r[0],
        rule: r[1],
        contract_sort: Number(r[2]),
        profit: Number(r[3])
      }));

    filteredData = allData;

    renderChart();

  }catch(err){

    console.warn("Data not loaded", err);

    document.getElementById("cumulativePLChart").innerHTML =
      "<p style='padding:20px'>No data available yet.</p>";

  }

}

  if(filteredData.length === 0){
    Plotly.purge("cumulativePLChart");
    return;
  }

  const grouped = {};

  // group rows by strategy
  filteredData.forEach(r=>{
    if(!grouped[r.rule]){
      grouped[r.rule] = [];
    }
    grouped[r.rule].push(r);
  });

  const traces = [];

  Object.keys(grouped).forEach(rule => {

    let cumulative = 0;

    const x = [];
    const y = [];

    grouped[rule]
      .sort((a,b)=>{
        if(a.date === b.date){
          return a.contract_sort - b.contract_sort;
        }
        return new Date(a.date) - new Date(b.date);
      })
      .forEach(r=>{
        cumulative += parseFloat(r.profit) || 0;

        x.push(r.contract_sort);   // clean x axis
        y.push(cumulative);
      });

    traces.push({
      x: x,
      y: y,
      mode: "lines",
      type: "scatter",
      name: rule
    });

  });

  Plotly.newPlot(
    "cumulativePLChart",
    traces,
    {
      title: "Cumulative Profit by Strategy",
      xaxis: { title: "Contract (15-min index)" },
      yaxis: { title: "Profit (€)" }
    }
  );
loadData();
}
