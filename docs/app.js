const DATA_URL = "data/latest.json";

async function loadData() {
    try {
        const response = await fetch(DATA_URL);

        if (!response.ok) {
            throw new Error("Failed to fetch data");
        }

        const data = await response.json();

        renderMetricCards(data);
        renderTable(data);
        renderChart(data);

    } catch (err) {
        console.error(err);
        showError();
    }
}

function renderMetricCards(data) {

    const container = document.getElementById("metrics");
    container.innerHTML = "";

    const prices = data.map(d => d.price);

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const avg = prices.reduce((a,b)=>a+b,0)/prices.length;

    const cards = [
        { label: "Min Price", value: min.toFixed(2) },
        { label: "Max Price", value: max.toFixed(2) },
        { label: "Average Price", value: avg.toFixed(2) }
    ];

    cards.forEach(card => {

        const el = document.createElement("div");
        el.className = "metric-card";

        el.innerHTML = `
            <h3>${card.label}</h3>
            <p>${card.value}</p>
        `;

        container.appendChild(el);

    });
}

function renderTable(data) {

    const tbody = document.querySelector("#priceTable tbody");
    tbody.innerHTML = "";

    data.forEach(item => {

        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>${item.hour}</td>
            <td>${item.price}</td>
        `;

        tbody.appendChild(tr);

    });
}

function renderChart(data) {

    const ctx = document.getElementById("priceChart").getContext("2d");

    const labels = data.map(d => d.hour);
    const prices = data.map(d => d.price);

    new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "Price",
                data: prices
            }]
        }
    });
}

function showError() {

    const container = document.querySelector(".container");

    container.innerHTML = `
        <div class="error">
            Failed to load data.
        </div>
    `;
}

loadData();
