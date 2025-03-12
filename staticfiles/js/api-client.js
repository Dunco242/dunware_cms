// static/js/api-client.js

class ApiClient {
    constructor() {
        this.baseUrl = '/api';
        this.token = this.getCsrfToken();
        this.handlers = new Map();
    }

    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    }

    setDefaultHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.token,
            'Accept': 'application/json'
        };
    }

    // Request builder with method chaining
    request(endpoint) {
        return new RequestBuilder(this, endpoint);
    }

    // API Endpoints for different entities
    customers = {
        list: (params) => this.request('/customers').withParams(params).get(),
        get: (id) => this.request(`/customers/${id}`).get(),
        create: (data) => this.request('/customers').withBody(data).post(),
        update: (id, data) => this.request(`/customers/${id}`).withBody(data).put(),
        delete: (id) => this.request(`/customers/${id}`).delete(),
        search: (query) => this.request('/customers/search').withParams({ q: query }).get()
    };

    leads = {
        list: (params) => this.request('/leads').withParams(params).get(),
        get: (id) => this.request(`/leads/${id}`).get(),
        create: (data) => this.request('/leads').withBody(data).post(),
        update: (id, data) => this.request(`/leads/${id}`).withBody(data).put(),
        delete: (id) => this.request(`/leads/${id}`).delete(),
        convert: (id) => this.request(`/leads/${id}/convert`).post()
    };

    tasks = {
        list: (params) => this.request('/tasks').withParams(params).get(),
        get: (id) => this.request(`/tasks/${id}`).get(),
        create: (data) => this.request('/tasks').withBody(data).post(),
        update: (id, data) => this.request(`/tasks/${id}`).withBody(data).put(),
        delete: (id) => this.request(`/tasks/${id}`).delete(),
        updateStatus: (id, status) => this.request(`/tasks/${id}/status`)
            .withBody({ status }).patch()
    };

    meetings = {
        list: (params) => this.request('/meetings').withParams(params).get(),
        get: (id) => this.request(`/meetings/${id}`).get(),
        create: (data) => this.request('/meetings').withBody(data).post(),
        update: (id, data) => this.request(`/meetings/${id}`).withBody(data).put(),
        delete: (id) => this.request(`/meetings/${id}`).delete(),
        getZoomLink: (id) => this.request(`/meetings/${id}/zoom-link`).get()
    };

    analytics = {
        getSummary: () => this.request('/analytics/summary').get(),
        getLeadsFunnel: () => this.request('/analytics/leads-funnel').get(),
        getSalesData: (period) => this.request('/analytics/sales')
            .withParams({ period }).get(),
        getCustomerGrowth: (period) => this.request('/analytics/customer-growth')
            .withParams({ period }).get()
    };

    // Error Handling
    handleError(error) {
        if (error.response) {
            switch (error.response.status) {
                case 401:
                    this.triggerHandler('unauthorized');
                    break;
                case 403:
                    this.triggerHandler('forbidden');
                    break;
                case 404:
                    this.triggerHandler('notFound');
                    break;
                case 422:
                    this.triggerHandler('validationError', error.response.data);
                    break;
                default:
                    this.triggerHandler('error', error);
            }
        } else {
            this.triggerHandler('networkError', error);
        }
        throw error;
    }

    // Event Handling
    on(event, handler) {
        if (!this.handlers.has(event)) {
            this.handlers.set(event, []);
        }
        this.handlers.get(event).push(handler);
    }

    off(event, handler) {
        if (this.handlers.has(event)) {
            const handlers = this.handlers.get(event);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    triggerHandler(event, data) {
        if (this.handlers.has(event)) {
            this.handlers.get(event).forEach(handler => handler(data));
        }
    }
}

// Request Builder Class
class RequestBuilder {
    constructor(client, endpoint) {
        this.client = client;
        this.endpoint = endpoint;
        this.params = new URLSearchParams();
        this.requestBody = null;
        this.requestHeaders = client.setDefaultHeaders();
    }

    withParams(params) {
        if (params) {
            Object.entries(params).forEach(([key, value]) => {
                if (value !== undefined && value !== null) {
                    this.params.append(key, value);
                }
            });
        }
        return this;
    }

    withBody(data) {
        this.requestBody = data;
        return this;
    }

    withHeaders(headers) {
        this.requestHeaders = { ...this.requestHeaders, ...headers };
        return this;
    }

    async execute(method) {
        const url = `${this.client.baseUrl}${this.endpoint}`;
        const queryString = this.params.toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        try {
            const response = await fetch(fullUrl, {
                method,
                headers: this.requestHeaders,
                body: this.requestBody ? JSON.stringify(this.requestBody) : null,
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw { response };
            }

            if (response.status === 204) {
                return null;
            }

            return await response.json();
        } catch (error) {
            return this.client.handleError(error);
        }
    }

    get() {
        return this.execute('GET');
    }

    post() {
        return this.execute('POST');
    }

    put() {
        return this.execute('PUT');
    }

    patch() {
        return this.execute('PATCH');
    }

    delete() {
        return this.execute('DELETE');
    }
}

// Initialize API client
const apiClient = new ApiClient();
export default apiClient;
