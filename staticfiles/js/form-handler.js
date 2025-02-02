// static/js/form-handler.js

class FormHandler {
    constructor() {
        this.forms = new Map();
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeForms();
            this.setupDynamicFormFields();
        });
    }

    initializeForms() {
        document.querySelectorAll('form[data-form-handler]').forEach(form => {
            this.registerForm(form);
        });
    }

    registerForm(form) {
        const formId = form.id || `form-${Math.random().toString(36).substr(2, 9)}`;
        form.id = formId;

        const formConfig = {
            validateOnInput: form.dataset.validateOnInput === 'true',
            ajaxSubmit: form.dataset.ajaxSubmit === 'true',
            resetOnSuccess: form.dataset.resetOnSuccess === 'true',
            successUrl: form.dataset.successUrl,
            successMessage: form.dataset.successMessage,
            errorMessage: form.dataset.errorMessage
        };

        this.forms.set(formId, formConfig);
        this.setupFormValidation(form, formConfig);
        this.setupFormSubmission(form, formConfig);
    }

    setupFormValidation(form, config) {
        if (config.validateOnInput) {
            form.querySelectorAll('input, select, textarea').forEach(field => {
                field.addEventListener('input', () => this.validateField(field));
                field.addEventListener('blur', () => this.validateField(field));
            });
        }
    }

    setupFormSubmission(form, config) {
        form.addEventListener('submit', async (e) => {
            if (config.ajaxSubmit) {
                e.preventDefault();
                await this.handleAjaxSubmit(form, config);
            } else {
                if (!this.validateForm(form)) {
                    e.preventDefault();
                }
            }
        });
    }

    async handleAjaxSubmit(form, config) {
        if (!this.validateForm(form)) {
            return;
        }

        const formData = new FormData(form);
        const submitButton = form.querySelector('[type="submit"]');
        submitButton.disabled = true;
        this.showFormLoading(form);

        try {
            const response = await fetch(form.action, {
                method: form.method,
                body: formData,
                headers: {
                    'X-CSRFToken': crmUtils.TOKEN
                }
            });

            const data = await response.json();

            if (response.ok) {
                this.handleFormSuccess(form, config, data);
            } else {
                this.handleFormError(form, config, data);
            }
        } catch (error) {
            this.handleFormError(form, config, { message: 'An unexpected error occurred' });
        } finally {
            submitButton.disabled = false;
            this.hideFormLoading(form);
        }
    }

    validateForm(form) {
        let isValid = true;
        form.querySelectorAll('input, select, textarea').forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });
        return isValid;
    }

    validateField(field) {
        const validators = {
            required: (value) => value.trim() !== '',
            email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
            minLength: (value, length) => value.length >= parseInt(length),
            maxLength: (value, length) => value.length <= parseInt(length),
            pattern: (value, pattern) => new RegExp(pattern).test(value),
            match: (value, targetId) => value === document.getElementById(targetId).value
        };

        let isValid = true;
        const errors = [];

        // Check all validators
        Object.keys(validators).forEach(validationType => {
            const validatorValue = field.dataset[validationType];
            if (validatorValue !== undefined) {
                if (!validators[validationType](field.value, validatorValue)) {
                    isValid = false;
                    errors.push(field.dataset[`${validationType}Message`] ||
                              `Field failed ${validationType} validation`);
                }
            }
        });

        this.updateFieldValidation(field, isValid, errors);
        return isValid;
    }

    updateFieldValidation(field, isValid, errors = []) {
        field.classList.toggle('is-invalid', !isValid);
        field.classList.toggle('is-valid', isValid);

        let feedbackElement = field.nextElementSibling;
        if (feedbackElement?.classList.contains('invalid-feedback')) {
            feedbackElement.remove();
        }

        if (!isValid) {
            feedbackElement = document.createElement('div');
            feedbackElement.className = 'invalid-feedback';
            feedbackElement.textContent = errors.join('. ');
            field.parentNode.insertBefore(feedbackElement, field.nextSibling);
        }
    }

    showFormLoading(form) {
        const loadingOverlay = document.createElement('div');
        loadingOverlay.className = 'form-loading-overlay';
        loadingOverlay.innerHTML = `
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        `;
        form.appendChild(loadingOverlay);
    }

    hideFormLoading(form) {
        const loadingOverlay = form.querySelector('.form-loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.remove();
        }
    }

    handleFormSuccess(form, config, data) {
        notificationSystem.success(config.successMessage || 'Form submitted successfully');

        if (config.resetOnSuccess) {
            form.reset();
        }

        if (config.successUrl) {
            window.location.href = config.successUrl;
        }

        form.dispatchEvent(new CustomEvent('formSubmitSuccess', { detail: data }));
    }

    handleFormError(form, config, data) {
        notificationSystem.error(config.errorMessage || data.message || 'Form submission failed');

        if (data.errors) {
            Object.entries(data.errors).forEach(([field, errors]) => {
                const fieldElement = form.querySelector(`[name="${field}"]`);
                if (fieldElement) {
                    this.updateFieldValidation(fieldElement, false, Array.isArray(errors) ? errors : [errors]);
                }
            });
        }

        form.dispatchEvent(new CustomEvent('formSubmitError', { detail: data }));
    }

    setupDynamicFormFields() {
        document.querySelectorAll('[data-dynamic-field]').forEach(field => {
            const targetField = document.getElementById(field.dataset.dynamicField);
            const sourceUrl = field.dataset.sourceUrl;

            field.addEventListener('change', async () => {
                try {
                    const response = await fetch(
                        `${sourceUrl}?value=${field.value}`,
                        { headers: { 'X-CSRFToken': crmUtils.TOKEN } }
                    );
                    const data = await response.json();
                    this.updateDynamicField(targetField, data);
                } catch (error) {
                    console.error('Error updating dynamic field:', error);
                }
            });
        });
    }

    updateDynamicField(field, data) {
        if (field.tagName === 'SELECT') {
            field.innerHTML = '';
            data.forEach(item => {
                const option = document.createElement('option');
                option.value = item.value;
                option.textContent = item.label;
                field.appendChild(option);
            });
        } else {
            field.value = data.value || '';
        }
    }
}

// Initialize form handler
const formHandler = new FormHandler();
export default formHandler;
