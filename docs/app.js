function renderChart(){

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

}
