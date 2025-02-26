// static/js/data-table-handler.js

class DataTableHandler {
    constructor() {
        this.tables = new Map();
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeTables();
        });
    }

    initializeTables() {
        document.querySelectorAll('table[data-table-handler]').forEach(table => {
            this.registerTable(table);
        });
    }

    registerTable(table) {
        const tableId = table.id || `table-${Math.random().toString(36).substr(2, 9)}`;
        table.id = tableId;

        const config = {
            sortable: table.dataset.sortable === 'true',
            filterable: table.dataset.filterable === 'true',
            pageable: table.dataset.pageable === 'true',
            pageSize: parseInt(table.dataset.pageSize) || 10,
            searchable: table.dataset.searchable === 'true',
            exportable: table.dataset.exportable === 'true',
            ajaxUrl: table.dataset.ajaxUrl,
            refreshInterval: parseInt(table.dataset.refreshInterval) || 0
        };

        this.tables.set(tableId, {
            element: table,
            config: config,
            currentPage: 1,
            sortColumn: null,
            sortDirection: 'asc',
            filters: new Map(),
            searchTerm: ''
        });

        this.setupTableFeatures(tableId);
        this.loadTableData(tableId);

        // Set up auto-refresh if configured
        if (config.refreshInterval > 0) {
            setInterval(() => this.loadTableData(tableId), config.refreshInterval * 1000);
        }
    }

    setupTableFeatures(tableId) {
        const table = this.tables.get(tableId);
        const { element, config } = table;

        this.createTableWrapper(tableId);

        if (config.searchable) {
            this.addSearchFeature(tableId);
        }

        if (config.filterable) {
            this.addFilterFeatures(tableId);
        }

        if (config.sortable) {
            this.addSortFeatures(tableId);
        }

        if (config.pageable) {
            this.addPaginationFeatures(tableId);
        }

        if (config.exportable) {
            this.addExportFeatures(tableId);
        }
    }

    createTableWrapper(tableId) {
        const table = this.tables.get(tableId);
        const wrapper = document.createElement('div');
        wrapper.className = 'table-responsive table-wrapper';

        const controls = document.createElement('div');
        controls.className = 'table-controls mb-3';

        table.element.parentNode.insertBefore(wrapper, table.element);
        wrapper.appendChild(controls);
        wrapper.appendChild(table.element);

        table.controls = controls;
    }

    addSearchFeature(tableId) {
        const table = this.tables.get(tableId);
        const searchDiv = document.createElement('div');
        searchDiv.className = 'table-search';
        searchDiv.innerHTML = `
            <div class="input-group">
                <input type="text" class="form-control" placeholder="Search...">
                <button class="btn btn-outline-secondary clear-search" type="button">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        table.controls.appendChild(searchDiv);

        const searchInput = searchDiv.querySelector('input');
        const clearButton = searchDiv.querySelector('.clear-search');

        searchInput.addEventListener('input', crmUtils.debounce(() => {
            table.searchTerm = searchInput.value;
            this.loadTableData(tableId);
        }, 300, 'tableSearch'));

        clearButton.addEventListener('click', () => {
            searchInput.value = '';
            table.searchTerm = '';
            this.loadTableData(tableId);
        });
    }

    addFilterFeatures(tableId) {
        const table = this.tables.get(tableId);
        const filterDiv = document.createElement('div');
        filterDiv.className = 'table-filters';

        // Add filter buttons based on column definitions
        table.element.querySelectorAll('th[data-filter]').forEach(th => {
            const filterName = th.dataset.filter;
            const filterOptions = th.dataset.filterOptions ?
                JSON.parse(th.dataset.filterOptions) : [];

            const filterSelect = document.createElement('select');
            filterSelect.className = 'form-select form-select-sm ms-2';
            filterSelect.innerHTML = `
                <option value="">All ${th.textContent}</option>
                ${filterOptions.map(option => `
                    <option value="${option.value}">${option.label}</option>
                `).join('')}
            `;

            filterSelect.addEventListener('change', () => {
                if (filterSelect.value) {
                    table.filters.set(filterName, filterSelect.value);
                } else {
                    table.filters.delete(filterName);
                }
                this.loadTableData(tableId);
            });

            filterDiv.appendChild(filterSelect);
        });

        table.controls.appendChild(filterDiv);
    }

    addSortFeatures(tableId) {
        const table = this.tables.get(tableId);

        table.element.querySelectorAll('th[data-sortable]').forEach(th => {
            th.classList.add('sortable');
            th.addEventListener('click', () => {
                const column = th.dataset.sortable;

                if (table.sortColumn === column) {
                    table.sortDirection = table.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    table.sortColumn = column;
                    table.sortDirection = 'asc';
                }

                this.updateSortIndicators(tableId);
                this.loadTableData(tableId);
            });
        });
    }

    updateSortIndicators(tableId) {
        const table = this.tables.get(tableId);

        table.element.querySelectorAll('th[data-sortable]').forEach(th => {
            th.classList.remove('sorting-asc', 'sorting-desc');
            if (th.dataset.sortable === table.sortColumn) {
                th.classList.add(`sorting-${table.sortDirection}`);
            }
        });
    }

    addPaginationFeatures(tableId) {
        const table = this.tables.get(tableId);
        const paginationDiv = document.createElement('div');
        paginationDiv.className = 'table-pagination mt-3';
        table.element.parentNode.appendChild(paginationDiv);

        table.paginationElement = paginationDiv;
    }

    updatePagination(tableId, totalItems) {
        const table = this.tables.get(tableId);
        const totalPages = Math.ceil(totalItems / table.config.pageSize);

        let paginationHtml = `
            <nav aria-label="Table pagination">
                <ul class="pagination justify-content-center">
                    <li class="page-item ${table.currentPage === 1 ? 'disabled' : ''}">
                        <a class="page-link" href="#" data-page="prev">Previous</a>
                    </li>
        `;

        for (let i = 1; i <= totalPages; i++) {
            paginationHtml += `
                <li class="page-item ${table.currentPage === i ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }

        paginationHtml += `
                    <li class="page-item ${table.currentPage === totalPages ? 'disabled' : ''}">
                        <a class="page-link" href="#" data-page="next">Next</a>
                    </li>
                </ul>
            </nav>
        `;

        table.paginationElement.innerHTML = paginationHtml;

        table.paginationElement.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.dataset.page;

                if (page === 'prev' && table.currentPage > 1) {
                    table.currentPage--;
                } else if (page === 'next' && table.currentPage < totalPages) {
                    table.currentPage++;
                } else if (page !== 'prev' && page !== 'next') {
                    table.currentPage = parseInt(page);
                }

                this.loadTableData(tableId);
            });
        });
    }

    addExportFeatures(tableId) {
        const table = this.tables.get(tableId);
        const exportDiv = document.createElement('div');
        exportDiv.className = 'table-export';
        exportDiv.innerHTML = `
            <div class="btn-group">
                <button class="btn btn-outline-secondary dropdown-toggle"
                        type="button" data-bs-toggle="dropdown">
                    Export
                </button>
                <ul class="dropdown-menu">
                    <li><a class="dropdown-item" href="#" data-export="csv">CSV</a></li>
                    <li><a class="dropdown-item" href="#" data-export="excel">Excel</a></li>
                    <li><a class="dropdown-item" href="#" data-export="pdf">PDF</a></li>
                </ul>
            </div>
        `;

        exportDiv.querySelectorAll('[data-export]').forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportTable(tableId, button.dataset.export);
            });
        });

        table.controls.appendChild(exportDiv);
    }

    async loadTableData(tableId) {
        const table = this.tables.get(tableId);
        if (!table.config.ajaxUrl) return;

        try {
            const params = new URLSearchParams({
                page: table.currentPage,
                pageSize: table.config.pageSize,
                search: table.searchTerm,
                sortColumn: table.sortColumn || '',
                sortDirection: table.sortDirection
            });

            table.filters.forEach((value, key) => {
                params.append(`filter[${key}]`, value);
            });

            const response = await fetch(`${table.config.ajaxUrl}?${params}`);
            const data = await response.json();

            this.renderTableData(tableId, data);
            this.updatePagination(tableId, data.total);
        } catch (error) {
            console.error('Error loading table data:', error);
            notificationSystem.error('Failed to load table data');
        }
    }

    renderTableData(tableId, data) {
        const table = this.tables.get(tableId);
        const tbody = table.element.querySelector('tbody');

        tbody.innerHTML = data.items.map(item => {
            const cells = table.element.querySelectorAll('th[data-field]').map(th => {
                const field = th.dataset.field;
                const template = th.dataset.template;

                if (template) {
                    return template.replace(/\${(\w+)}/g, (_, key) => item[key]);
                } else {
                    return item[field];
                }
            }).join('');

            return `<tr>${cells}</tr>`;
        }).join('');
    }

    async exportTable(tableId, format) {
        const table = this.tables.get(tableId);

        try {
            const response = await fetch(`${table.config.ajaxUrl}/export`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': crmUtils.TOKEN
                },
                body: JSON.stringify({
                    format,
                    filters: Object.fromEntries(table.filters),
                    search: table.searchTerm,
                    sortColumn: table.sortColumn,
                    sortDirection: table.sortDirection
                })
            });

            if (!response.ok) throw new Error('Export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `export.${format}`;
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Export error:', error);
            notificationSystem.error('Failed to export table data');
        }
    }
}

// Initialize data table handler
const dataTableHandler = new DataTableHandler();
export default dataTableHandler;
