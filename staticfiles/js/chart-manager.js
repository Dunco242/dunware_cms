// static/js/chart-manager.js

class ChartManager {
    constructor() {
        this.charts = new Map();
        this.defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        };
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeCharts();
            this.setupResizeHandler();
            this.setupThemeHandler();
        });
    }

    initializeCharts() {
        document.querySelectorAll('[data-chart]').forEach(canvas => {
            this.createChart(canvas);
        });
    }

    createChart(canvas) {
        const type = canvas.dataset.chart;
        const endpoint = canvas.dataset.endpoint;
        const refreshInterval = parseInt(canvas.dataset.refresh) || 0;
        const options = this.getChartOptions(canvas);

        this.loadChartData(canvas.id, endpoint).then(data => {
            const chart = new Chart(canvas, {
                type,
                data,
                options: { ...this.defaultOptions, ...options }
            });

            this.charts.set(canvas.id, {
                instance: chart,
                endpoint,
                refreshInterval
            });

            if (refreshInterval > 0) {
                this.setupAutoRefresh(canvas.id, refreshInterval);
            }
        });
    }

    getChartOptions(canvas) {
        try {
            return JSON.parse(canvas.dataset.options || '{}');
        } catch (error) {
            console.error('Invalid chart options:', error);
            return {};
        }
    }

    async loadChartData(chartId, endpoint) {
        try {
            const response = await apiClient.request(endpoint).get();
            return this.processChartData(response);
        } catch (error) {
            console.error('Error loading chart data:', error);
            notificationSystem.error('Failed to load chart data');
            return {
                labels: [],
                datasets: []
            };
        }
    }

    processChartData(data) {
        // Process different data formats based on chart type
        if (data.datasets) {
            return data;
        }

        // Convert simple array data to chart format
        if (Array.isArray(data)) {
            return {
                labels: data.map(item => item.label),
                datasets: [{
                    data: data.map(item => item.value)
                }]
            };
        }

        return data;
    }

    setupAutoRefresh(chartId, interval) {
        setInterval(() => this.refreshChart(chartId), interval * 1000);
    }

    async refreshChart(chartId) {
        const chart = this.charts.get(chartId);
        if (!chart) return;

        try {
            const data = await this.loadChartData(chartId, chart.endpoint);
            chart.instance.data = data;
            chart.instance.update();
        } catch (error) {
            console.error('Error refreshing chart:', error);
        }
    }

    setupResizeHandler() {
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                this.charts.forEach(chart => chart.instance.resize());
            }, 250);
        });
    }

    setupThemeHandler() {
        // Handle theme changes (light/dark mode)
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        const updateChartsTheme = (isDark) => {
            Chart.defaults.color = isDark ? '#fff' : '#666';
            Chart.defaults.borderColor = isDark ? '#444' : '#ddd';

            this.charts.forEach(chart => {
                chart.instance.update();
            });
        };

        mediaQuery.addListener((e) => updateChartsTheme(e.matches));
        updateChartsTheme(mediaQuery.matches);
    }

    // Public methods for external use
    getChart(chartId) {
        return this.charts.get(chartId)?.instance;
    }

    updateChart(chartId, newData) {
        const chart = this.charts.get(chartId);
        if (chart) {
            chart.instance.data = this.processChartData(newData);
            chart.instance.update();
        }
    }

    destroyChart(chartId) {
        const chart = this.charts.get(chartId);
        if (chart) {
            chart.instance.destroy();
            this.charts.delete(chartId);
        }
    }
}

// Initialize chart manager
const chartManager = new ChartManager();
export default chartManager;
