// Nordpool Market Analysis Dashboard
// Main application logic for data loading, filtering, and visualization

// Global state
let allData = [];
let filteredData = [];
let selectors = {};

// Initialize the application when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded - Starting application initialization');
    loadData();
    setupEventListeners();
    updateLastUpdatedTime();
});

/**
 * Load data from JSON files
 */
function loadData() {
    console.log('Loading data from JSON files...');
    
    // Load contract profits data
    fetch('data/contract_profits.json')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Contract profits data loaded:', data.length, 'records');
            allData = data;
            filteredData = [...allData];
            
            // Load selector options
            return fetch('data/selector_options.json');
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Selector options loaded');
            selectors = data;
            populateSelectors();
            renderCharts();
            renderTables();
        })
        .catch(error => {
            console.error('Error loading data:', error);
            showError('Failed to load data. Please refresh the page.');
        });
}

/**
 * Populate filter dropdowns with unique values
 */
function populateSelectors() {
    console.log('Populating selectors with options');
    
    const areaSelect = document.getElementById('area');
    const strategySelect = document.getElementById('strategy');
    const directionSelect = document.getElementById('direction');
    const contractSelect = document.getElementById('contract');
    
    if (!areaSelect || !strategySelect || !directionSelect || !contractSelect) {
        console.warn('Some select elements not found in DOM');
        return;
    }
    
    // Populate Area
    if (selectors.areas) {
        selectors.areas.forEach(area => {
            const option = document.createElement('option');
            option.value = area;
            option.textContent = area;
            areaSelect.appendChild(option);
        });
    }
    
    // Populate Strategy
    if (selectors.strategies) {
        selectors.strategies.forEach(strategy => {
            const option = document.createElement('option');
            option.value = strategy;
            option.textContent = strategy;
            strategySelect.appendChild(option);
        });
    }
    
    // Populate Direction
    if (selectors.directions) {
        selectors.directions.forEach(direction => {
            const option = document.createElement('option');
            option.value = direction;
            option.textContent = direction;
            directionSelect.appendChild(option);
        });
    }
    
    // Populate Contract
    if (selectors.contracts) {
        selectors.contracts.forEach(contract => {
            const option = document.createElement('option');
            option.value = contract;
            option.textContent = contract;
            contractSelect.appendChild(option);
        });
    }
    
    console.log('Selectors populated successfully');
}

/**
 * Setup event listeners for filters
 */
function setupEventListeners() {
    console.log('Setting up event listeners');
    
    const areaSelect = document.getElementById('area');
    const strategySelect = document.getElementById('strategy');
    const directionSelect = document.getElementById('direction');
    const contractSelect = document.getElementById('contract');
    
    if (areaSelect) areaSelect.addEventListener('change', applyFilters);
    if (strategySelect) strategySelect.addEventListener('change', applyFilters);
    if (directionSelect) directionSelect.addEventListener('change', applyFilters);
    if (contractSelect) contractSelect.addEventListener('change', applyFilters);
    
    console.log('Event listeners setup complete');
}

/**
 * Apply filters to data
 */
function applyFilters() {
    console.log('Applying filters...');
    
    const area = document.getElementById('area')?.value || '';
    const strategy = document.getElementById('strategy')?.value || '';
    const direction = document.getElementById('direction')?.value || '';
    const contract = document.getElementById('contract')?.value || '';
    
    filteredData = allData.filter(record => {
        const areaMatch = !area || record.area === area;
        const strategyMatch = !strategy || record.rule === strategy;
        const directionMatch = !direction || record.direction === direction;
        const contractMatch = !contract || record.contract === contract;
        
        return areaMatch && strategyMatch && directionMatch && contractMatch;
    });
    
    console.log('Filters applied. Filtered records:', filteredData.length);
    
    renderCharts();
    renderTables();
}

/**
 * Select specific contracts
 */
function selectContracts(contracts) {
    console.log('Selecting contracts:', contracts);
    
    const contractSelect = document.getElementById('contract');
    if (contractSelect) {
        contractSelect.value = '';
    }
    
    filteredData = allData.filter(record => {
        return contracts.includes(record.contract);
    });
    
    console.log('Contract selection applied. Filtered records:', filteredData.length);
    
    renderCharts();
    renderTables();
}

/**
 * Render all charts
 */
function renderCharts() {
    console.log('Rendering charts...');
    
    if (filteredData.length === 0) {
        showEmptyState();
        return;
    }
    
    renderCumulativePLChart();
    renderProfitDistributionChart();
    renderHeatmapChart();
    renderContractPerformanceChart();
    renderPriceComparisonChart();
}

/**
 * Render cumulative P&L chart
 */
function renderCumulativePLChart() {
    const container = document.getElementById('cumulativePLChart');
    if (!container) return;
    
    // Sort data by date
    const sortedData = [...filteredData].sort((a, b) => new Date(a.date) - new Date(b.date));
    
    let cumulativeProfit = 0;
    const dates = [];
    const profits = [];
    
    sortedData.forEach(record => {
        cumulativeProfit += parseFloat(record.profit) || 0;
        dates.push(record.date);
        profits.push(cumulativeProfit);
    });
    
    const trace = {
        x: dates,
        y: profits,
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Cumulative P&L',
        line: {
            color: '#2575d4',
            width: 2
        },
        fill: 'tozeroy',
        fillcolor: 'rgba(37, 117, 212, 0.2)',
        marker: {
            size: 4,
            color: '#2575d4'
        }
    };
    
    const layout = {
        title: '',
        xaxis: { title: 'Date' },
        yaxis: { title: 'Profit/Loss' },
        hovermode: 'x unified',
        plot_bgcolor: '#1a1a2e',
        paper_bgcolor: '#1a1a2e',
        font: { color: '#f1f5f9' },
        margin: { t: 20, b: 40, l: 60, r: 20 }
    };
    
    Plotly.newPlot(container, [trace], layout, { responsive: true });
}

/**
 * Render profit distribution histogram
 */
function renderProfitDistributionChart() {
    const container = document.getElementById('profitDistributionChart');
    if (!container) return;
    
    const profits = filteredData.map(record => parseFloat(record.profit) || 0);
    
    const trace = {
        x: profits,
        type: 'histogram',
        nbinsx: 30,
        name: 'Profit Distribution',
        marker: {
            color: '#10b981',
            opacity: 0.7
        }
    };
    
    const layout = {
        title: '',
        xaxis: { title: 'Profit/Loss' },
        yaxis: { title: 'Frequency' },
        plot_bgcolor: '#1a1a2e',
        paper_bgcolor: '#1a1a2e',
        font: { color: '#f1f5f9' },
        margin: { t: 20, b: 40, l: 60, r: 20 }
    };
    
    Plotly.newPlot(container, [trace], layout, { responsive: true });
}

/**
 * Render heatmap of areas and contracts
 */
function renderHeatmapChart() {
    const container = document.getElementById('heatmapChart');
    if (!container) return;
    
    // Group data by area and contract
    const heatmapData = {};
    
    filteredData.forEach(record => {
        const key = `${record.area}_${record.contract}`;
        if (!heatmapData[key]) {
            heatmapData[key] = [];
        }
        heatmapData[key].push(parseFloat(record.profit) || 0);
    });
    
    // Calculate average profit for each combination
    const areas = [...new Set(filteredData.map(r => r.area))].sort();
    const contracts = [...new Set(filteredData.map(r => r.contract))].sort();
    
    const zValues = areas.map(area => {
        return contracts.map(contract => {
            const key = `${area}_${contract}`;
            const profits = heatmapData[key] || [0];
            const avg = profits.reduce((a, b) => a + b, 0) / profits.length;
            return avg;
        });
    });
    
    const trace = {
        z: zValues,
        x: contracts,
        y: areas,
        type: 'heatmap',
        colorscale: [
            [0, '#dc2626'],
            [0.5, '#f1f5f9'],
            [1, '#10b981']
        ],
        hovertemplate: 'Area: %{y}<br>Contract: %{x}<br>Avg Profit: %{z:.2f}<extra></extra>'
    };
    
    const layout = {
        title: '',
        xaxis: { title: 'Contract Type' },
        yaxis: { title: 'Market Area' },
        plot_bgcolor: '#1a1a2e',
        paper_bgcolor: '#1a1a2e',
        font: { color: '#f1f5f9' },
        margin: { t: 20, b: 40, l: 100, r: 20 }
    };
    
    Plotly.newPlot(container, [trace], layout, { responsive: true });
}

/**
 * Render contract performance comparison
 */
function renderContractPerformanceChart() {
    const container = document.getElementById('contractPerformanceChart');
    if (!container) return;
    
    // Group by contract and calculate metrics
    const contractMetrics = {};
    
    filteredData.forEach(record => {
        if (!contractMetrics[record.contract]) {
            contractMetrics[record.contract] = {
                totalProfit: 0,
                count: 0,
                wins: 0
            };
        }
        
        const profit = parseFloat(record.profit) || 0;
        contractMetrics[record.contract].totalProfit += profit;
        contractMetrics[record.contract].count += 1;
        if (profit > 0) {
            contractMetrics[record.contract].wins += 1;
        }
    });
    
    const contracts = Object.keys(contractMetrics).sort();
    const avgProfits = contracts.map(c => contractMetrics[c].totalProfit / contractMetrics[c].count);
    const winRates = contracts.map(c => (contractMetrics[c].wins / contractMetrics[c].count) * 100);
    
    const trace1 = {
        x: contracts,
        y: avgProfits,
        type: 'bar',
        name: 'Avg Profit',
        marker: { color: '#2575d4' }
    };
    
    const trace2 = {
        x: contracts,
        y: winRates,
        type: 'bar',
        name: 'Win Rate (%)',
        marker: { color: '#10b981' },
        yaxis: 'y2'
    };
    
    const layout = {
        title: '',
        xaxis: { title: 'Contract Type' },
        yaxis: { title: 'Avg Profit' },
        yaxis2: { title: 'Win Rate (%)', overlaying: 'y', side: 'right' },
        barmode: 'group',
        plot_bgcolor: '#1a1a2e',
        paper_bgcolor: '#1a1a2e',
        font: { color: '#f1f5f9' },
        margin: { t: 20, b: 40, l: 60, r: 60 }
    };
    
    Plotly.newPlot(container, [trace1, trace2], layout, { responsive: true });
}

/**
 * Render price comparison chart
 */
function renderPriceComparisonChart() {
    const container = document.getElementById('priceComparisonChart');
    if (!container) return;
    
    // Group by area and calculate average prices
    const areaMetrics = {};
    
    filteredData.forEach(record => {
        if (!areaMetrics[record.area]) {
            areaMetrics[record.area] = {
                buyPrices: [],
                sellPrices: []
            };
        }
        
        areaMetrics[record.area].buyPrices.push(parseFloat(record.buy_price) || 0);
        areaMetrics[record.area].sellPrices.push(parseFloat(record.sell_price) || 0);
    });
    
    const areas = Object.keys(areaMetrics).sort();
    const avgBuyPrices = areas.map(a => {
        const prices = areaMetrics[a].buyPrices;
        return prices.reduce((a, b) => a + b, 0) / prices.length;
    });
    const avgSellPrices = areas.map(a => {
        const prices = areaMetrics[a].sellPrices;
        return prices.reduce((a, b) => a + b, 0) / prices.length;
    });
    
    const trace1 = {
        x: areas,
        y: avgBuyPrices,
        type: 'bar',
        name: 'Avg Buy Price',
        marker: { color: '#f59e0b' }
    };
    
    const trace2 = {
        x: areas,
        y: avgSellPrices,
        type: 'bar',
        name: 'Avg Sell Price',
        marker: { color: '#10b981' }
    };
    
    const layout = {
        title: '',
        xaxis: { title: 'Market Area' },
        yaxis: { title: 'Price' },
        barmode: 'group',
        plot_bgcolor: '#1a1a2e',
        paper_bgcolor: '#1a1a2e',
        font: { color: '#f1f5f9' },
        margin: { t: 20, b: 40, l: 60, r: 20 }
    };
    
    Plotly.newPlot(container, [trace1, trace2], layout, { responsive: true });
}

/**
 * Render data tables
 */
function renderTables() {
    renderTopPerformersTable();
    renderBottomPerformersTable();
}

/**
 * Render top performers table
 */
function renderTopPerformersTable() {
    const container = document.getElementById('topPerformersTable');
    if (!container) return;
    
    const sorted = [...filteredData].sort((a, b) => parseFloat(b.profit) - parseFloat(a.profit));
    const top = sorted.slice(0, 10);
    
    let html = '<table><thead><tr><th>Date</th><th>Area</th><th>Contract</th><th>Strategy</th><th>Buy Price</th><th>Sell Price</th><th>Profit</th></tr></thead><tbody>';
    
    top.forEach(record => {
        const profitClass = parseFloat(record.profit) >= 0 ? 'positive' : 'negative';
        html += `<tr>
            <td>${record.date}</td>
            <td>${record.area}</td>
            <td>${record.contract}</td>
            <td>${record.rule}</td>
            <td>${parseFloat(record.buy_price).toFixed(2)}</td>
            <td>${parseFloat(record.sell_price).toFixed(2)}</td>
            <td class="${profitClass}">${parseFloat(record.profit).toFixed(2)}</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

/**
 * Render bottom performers table
 */
function renderBottomPerformersTable() {
    const container = document.getElementById('bottomPerformersTable');
    if (!container) return;
    
    const sorted = [...filteredData].sort((a, b) => parseFloat(a.profit) - parseFloat(b.profit));
    const bottom = sorted.slice(0, 10);
    
    let html = '<table><thead><tr><th>Date</th><th>Area</th><th>Contract</th><th>Strategy</th><th>Buy Price</th><th>Sell Price</th><th>Profit</th></tr></thead><tbody>';
    
    bottom.forEach(record => {
        const profitClass = parseFloat(record.profit) >= 0 ? 'positive' : 'negative';
        html += `<tr>
            <td>${record.date}</td>
            <td>${record.area}</td>
            <td>${record.contract}</td>
            <td>${record.rule}</td>
            <td>${parseFloat(record.buy_price).toFixed(2)}</td>
            <td>${parseFloat(record.sell_price).toFixed(2)}</td>
            <td class="${profitClass}">${parseFloat(record.profit).toFixed(2)}</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

/**
 * Show empty state message
 */
function showEmptyState() {
    const charts = ['cumulativePLChart', 'profitDistributionChart', 'heatmapChart', 'contractPerformanceChart', 'priceComparisonChart'];
    
    charts.forEach(chartId => {
        const container = document.getElementById(chartId);
        if (container) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-title">No Data Available</div><p>Try adjusting your filters to see results.</p></div>';
        }
    });
    
    document.getElementById('topPerformersTable').innerHTML = '<p style="text-align: center; color: #cbd5e1; padding: 2rem;">No data matches your filters.</p>';
    document.getElementById('bottomPerformersTable').innerHTML = '<p style="text-align: center; color: #cbd5e1; padding: 2rem;">No data matches your filters.</p>';
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.querySelector('.container');
    if (container) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = '❌ ' + message;
        container.insertBefore(errorDiv, container.firstChild);
    }
}

/**
 * Update last updated time
 */
function updateLastUpdatedTime() {
    const element = document.getElementById('lastUpdated');
    if (element) {
        const now = new Date();
        element.textContent = now.toLocaleString();
    }
}
