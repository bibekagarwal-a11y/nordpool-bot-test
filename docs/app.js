let data = [];

async function loadData(){

const res = await fetch("data/contract_profits.json");
data = await res.json();

populateSelectors();

}

function unique(arr){
return [...new Set(arr)];
}

function populateSelectors(){

const areas = unique(data.map(x => x.area));
const rules = unique(data.map(x => x.rule));

setOptions("area",areas);
setOptions("rule",rules);

updateDates();

}

function setOptions(id,values){

const el = document.getElementById(id);
el.innerHTML="";

values.forEach(v=>{
let opt=document.createElement("option");
opt.value=v;
opt.text=v;
el.appendChild(opt);
});

}

function updateDates(){

let area = document.getElementById("area").value;
let rule = document.getElementById("rule").value;

let filtered = data.filter(d=>d.area==area && d.rule==rule);

let dates = unique(filtered.map(x=>x.date));

setOptions("date",dates);

updateContracts();

}

function updateContracts(){

let area = document.getElementById("area").value;
let rule = document.getElementById("rule").value;
let date = document.getElementById("date").value;

let filtered = data.filter(d=>
d.area==area &&
d.rule==rule &&
d.date==date
);

filtered.sort((a,b)=>a.contract_sort-b.contract_sort);

setOptions("contracts",filtered.map(x=>x.contract));

render();

}

function render(){

let area = document.getElementById("area").value;
let rule = document.getElementById("rule").value;
let date = document.getElementById("date").value;

let selected=[...document.getElementById("contracts").selectedOptions].map(x=>x.value);

let filtered=data.filter(d=>
d.area==area &&
d.rule==rule &&
d.date==date &&
selected.includes(d.contract)
);

let profits=filtered.map(x=>Number(x.profit));

let total=profits.reduce((a,b)=>a+b,0);

document.getElementById("profit").innerText=total.toFixed(2)+" €/MWh";

Plotly.newPlot("histogram",[
{
x:profits,
type:"histogram"
}
]);

let rows=filtered.map(d=>
`<tr>
<td>${d.contract}</td>
<td>${d.buy_price.toFixed(2)}</td>
<td>${d.sell_price.toFixed(2)}</td>
<td>${d.profit.toFixed(2)}</td>
</tr>`
).join("");

document.getElementById("table").innerHTML=`

<table>

<tr>
<th>Contract</th>
<th>Buy</th>
<th>Sell</th>
<th>Profit</th>
</tr>

${rows}

</table>

`;

}

document.getElementById("area").addEventListener("change",updateDates);
document.getElementById("rule").addEventListener("change",updateDates);
document.getElementById("date").addEventListener("change",updateContracts);
document.getElementById("contracts").addEventListener("change",render);

loadData();
