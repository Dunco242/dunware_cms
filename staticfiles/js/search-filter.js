// static/js/search-filter.js

class SearchFilterManager {
    constructor() {
        this.filters = new Map();
        this.searchDebounceTime = 300;
        this.activeSearches = new Map();
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeSearchFields();
            this.initializeFilters();
            this.initializeSortingElements();
        });
    }

    initializeSearchFields() {
        document.querySelectorAll('[data-search]').forEach(element => {
            const config = {
                target: element.dataset.searchTarget,
                url: element.dataset.searchUrl,
                minLength: parseInt(element.dataset.searchMin) || 2,
                resultTemplate: element.dataset.searchTemplate,
                params: this.parseDataAttributes(element, 'search-param-')
            };

            element.addEventListener('input', crmUtils.debounce(() => {
                this.handleSearch(element, config);
            }, this.searchDebounceTime));

            // Clear search button
            if (element.dataset.searchClear) {
                const clearButton = document.querySelector(element.dataset.searchClear);
                if (clearButton) {
                    clearButton.addEventListener('click', () => {
                        element.value = '';
                        this.clearSearch(element, config);
                    });
                }
            }
        });
    }

    initializeFilters() {
        document.querySelectorAll('[data-filter]').forEach(element => {
            const config = {
                target: element.dataset.filterTarget,
                url: element.dataset.filterUrl,
                type: element.dataset.filterType || 'select',
                params: this.parseDataAttributes(element, 'filter-param-')
            };

            this.filters.set(element.id, config);

            element.addEventListener('change', () => {
                this.handleFilter(element, config);
            });
        });
    }

    initializeSortingElements() {
        document.querySelectorAll('[data-sort]').forEach(element => {
            element.addEventListener('click', () => {
                this.handleSort(element);
            });
        });
    }

    async handleSearch(element, config) {
        const query = element.value.trim();
        const targetElement = document.querySelector(config.target);

        if (!targetElement) return;

        if (query.length < config.minLength) {
            this.clearSearch(element, config);
            return;
        }

        try {
            const params = new URLSearchParams({
                q: query,
                ...config.params
            });

            const response = await apiClient.request(`${config.url}?${params}`).get();
            this.updateSearchResults(targetElement, response, config);
        } catch (error) {
            console.error('Search error:', error);
            notificationSystem.error('Error performing search');
        }
    }

    clearSearch(element, config) {
        const targetElement = document.querySelector(config.target);
        if (targetElement) {
            targetElement.innerHTML = '';
            targetElement.classList.remove('has-results');
        }
    }

    updateSearchResults(targetElement, results, config) {
        targetElement.innerHTML = '';

        if (results.length === 0) {
            targetElement.innerHTML = '<div class="no-results">No results found</div>';
            return;
        }

        const template = config.resultTemplate || this.getDefaultTemplate();
        const resultsHtml = results.map(result => {
            return template.replace(/\${(\w+)}/g, (_, key) => result[key] || '');
        }).join('');

        targetElement.innerHTML = resultsHtml;
        targetElement.classList.add('has-results');
    }

    async handleFilter(element, config) {
        const targetElement = document.querySelector(config.target);
        if (!targetElement) return;

        const filters = this.collectActiveFilters();
        try {
            const params = new URLSearchParams(filters);
            const response = await apiClient.request(`${config.url}?${params}`).get();
            this.updateFilteredResults(targetElement, response, config);
        } catch (error) {
            console.error('Filter error:', error);
            notificationSystem.error('Error applying filters');
        }
    }

    collectActiveFilters() {
        const filters = {};
        this.filters.forEach((config, elementId) => {
            const element = document.getElementById(elementId);
            if (element) {
                const value = this.getElementValue(element);
                if (value) {
                    filters[element.name] = value;
                }
            }
        });
        return filters;
    }

    getElementValue(element) {
        if (element.type === 'checkbox') {
            return element.checked ? element.value : '';
        } else if (element.type === 'radio') {
            return element.checked ? element.value : '';
        } else if (element.multiple) {
            return Array.from(element.selectedOptions).map(option => option.value);
        }
        return element.value;
    }

    handleSort(element) {
        const column = element.dataset.sort;
        const currentDirection = element.dataset.sortDirection || 'asc';
        const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';

        // Update sort indicators
        document.querySelectorAll('[data-sort]').forEach(el => {
            el.dataset.sortDirection = '';
            el.classList.remove('sort-asc', 'sort-desc');
        });

        element.dataset.sortDirection = newDirection;
        element.classList.add(`sort-${newDirection}`);

        // Trigger sort event
        const event = new CustomEvent('sort', {
            detail: { column, direction: newDirection }
        });
        element.dispatchEvent(event);
    }

    parseDataAttributes(element, prefix) {
        const params = {};
        const prefixLength = prefix.length;

        Object.keys(element.dataset).forEach(key => {
            if (key.startsWith(prefix)) {
                const paramName = key.substring(prefixLength);
                params[paramName] = element.dataset[key];
            }
        });

        return params;
    }

    getDefaultTemplate() {
        return `
            <div class="search-result">
                <div class="search-result-title">\${title}</div>
                <div class="search-result-description">\${description}</div>
            </div>
        `;
    }
}

// Initialize search filter manager
const searchFilterManager = new SearchFilterManager();
export default searchFilterManager;
