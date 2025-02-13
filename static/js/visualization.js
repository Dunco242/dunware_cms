// static/js/visualization.js

class CRMDataVisualization {
    constructor() {
        this.charts = {};
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeCharts();
            this.setupEventListeners();
        });
    }

    initializeCharts() {
        this.initializeLeadsFunnel();
        this.initializeSalesChart();
        this.initializeTasksDistribution();
        this.initializeCustomerGrowth();
    }

    async initializeLeadsFunnel() {
        const ctx = document.getElementById('leadsFunnel');
        if (!ctx) return;

        try {
            const data = await this.fetchLeadsData();
            this.charts.leadsFunnel = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Leads by Stage',
                        data: data.values,
                        backgroundColor: [
                            'rgba(78, 115, 223, 0.8)',
                            'rgba(54, 185, 204, 0.8)',
                            'rgba(28, 200, 138, 0.8)',
                            'rgba(246, 194, 62, 0.8)',
                            'rgba(231, 74, 59, 0.8)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error initializing leads funnel:', error);
        }
    }

    async initializeSalesChart() {
        const ctx = document.getElementById('salesChart');
        if (!ctx) return;

        try {
            const data = await this.fetchSalesData();
            this.charts.sales = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Revenue',
                        data: data.revenue,
                        borderColor: 'rgba(78, 115, 223, 1)',
                        fill: false
                    }, {
                        label: 'Expenses',
                        data: data.expenses,
                        borderColor: 'rgba(231, 74, 59, 1)',
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return '$' + value.toLocaleString();
                                }
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error initializing sales chart:', error);
        }
    }

    async initializeTasksDistribution() {
        const ctx = document.getElementById('tasksDistribution');
        if (!ctx) return;

        try {
            const data = await this.fetchTasksData();
            this.charts.tasks = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.values,
                        backgroundColor: [
                            'rgba(231, 74, 59, 0.8)',
                            'rgba(246, 194, 62, 0.8)',
                            'rgba(54, 185, 204, 0.8)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        } catch (error) {
            console.error('Error initializing tasks distribution:', error);
        }
    }

    async initializeCustomerGrowth() {
        const ctx = document.getElementById('customerGrowth');
        if (!ctx) return;

        try {
            const data = await this.fetchCustomerGrowthData();
            this.charts.customerGrowth = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'New Customers',
                        data: data.values,
                        borderColor: 'rgba(28, 200, 138, 1)',
                        fill: true,
                        backgroundColor: 'rgba(28, 200, 138, 0.1)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error initializing customer growth chart:', error);
        }
    }

    // Data fetching methods
    async fetchLeadsData() {
        const response = await fetch('/api/analytics/leads-funnel/');
        return await response.json();
    }

    async fetchSalesData() {
        const response = await fetch('/api/analytics/sales/');
        return await response.json();
    }

    async fetchTasksData() {
        const response = await fetch('/api/analytics/tasks-distribution/');
        return await response.json();
    }

    async fetchCustomerGrowthData() {
        const response = await fetch('/api/analytics/customer-growth/');
        return await response.json();
    }

    // Event listeners and update methods
    setupEventListeners() {
        // Date range selector
        const dateRange = document.getElementById('dateRange');
        if (dateRange) {
            dateRange.addEventListener('change', () => this.updateCharts());
        }

        // Refresh button
        const refreshBtn = document.getElementById('refreshCharts');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshAllCharts());
        }
    }

    async updateCharts() {
        const dateRange = document.getElementById('dateRange').value;
        await Promise.all([
            this.updateSalesChart(dateRange),
            this.updateCustomerGrowthChart(dateRange)
        ]);
    }

    async refreshAllCharts() {
        this.showLoadingIndicator(true);
        try {
            await Promise.all([
                this.initializeLeadsFunnel(),
                this.initializeSalesChart(),
                this.initializeTasksDistribution(),
                this.initializeCustomerGrowth()
            ]);
            this.showNotification('Charts refreshed successfully', 'success');
        } catch (error) {
            console.error('Error refreshing charts:', error);
            this.showNotification('Failed to refresh charts', 'error');
        } finally {
            this.showLoadingIndicator(false);
        }
    }

    showLoadingIndicator(show) {
        const loader = document.getElementById('chartsLoader');
        if (loader) {
            loader.style.display = show ? 'block' : 'none';
        }
    }

    showNotification(message, type) {
        // Reuse the notification system from the calendar
        if (window.crmCalendar) {
            window.crmCalendar.showNotification(message, type);
        }
    }
}

// Initialize visualizations
const crmVisualization = new CRMDataVisualization();
