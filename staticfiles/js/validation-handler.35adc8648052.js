// static/js/validation-handler.js

class ValidationHandler {
    constructor() {
        this.rules = new Map();
        this.customValidators = new Map();
        this.init();
    }

    init() {
        // Register default validators
        this.registerDefaultValidators();

        // Initialize validation on forms
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeForms();
        });
    }

    registerDefaultValidators() {
        this.addValidator('required', (value) => {
            return value !== null && value !== undefined && value.toString().trim() !== '';
        }, 'This field is required');

        this.addValidator('email', (value) => {
            return !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
        }, 'Please enter a valid email address');

        this.addValidator('phone', (value) => {
            return !value || /^\+?[\d\s-()]+$/.test(value);
        }, 'Please enter a valid phone number');

        this.addValidator('url', (value) => {
            try {
                return !value || Boolean(new URL(value));
            } catch {
                return false;
            }
        }, 'Please enter a valid URL');

        this.addValidator('minLength', (value, params) => {
            return !value || value.length >= parseInt(params);
        }, (params) => `Minimum length is ${params} characters`);

        this.addValidator('maxLength', (value, params) => {
            return !value || value.length <= parseInt(params);
        }, (params) => `Maximum length is ${params} characters`);

        this.addValidator('regex', (value, pattern) => {
            return !value || new RegExp(pattern).test(value);
        }, 'Please enter a valid value');

        this.addValidator('number', (value) => {
            return !value || !isNaN(parseFloat(value));
        }, 'Please enter a valid number');

        this.addValidator('min', (value, min) => {
            return !value || parseFloat(value) >= parseFloat(min);
        }, (min) => `Minimum value is ${min}`);

        this.addValidator('max', (value, max) => {
            return !value || parseFloat(value) <= parseFloat(max);
        }, (max) => `Maximum value is ${max}`);
    }

    addValidator(name, validator, message) {
        this.customValidators.set(name, {
            validate: validator,
            message: typeof message === 'function' ? message : () => message
        });
    }

    initializeForms() {
        document.querySelectorAll('form[data-validate]').forEach(form => {
            this.initializeForm(form);
        });
    }

    initializeForm(form) {
        // Store validation rules
        this.storeFormRules(form);

        // Add form event listeners
        form.addEventListener('submit', (e) => this.handleFormSubmit(e));

        // Add field event listeners
        form.querySelectorAll('[data-validate]').forEach(field => {
            field.addEventListener('blur', () => this.validateField(field));
            field.addEventListener('input', () => this.validateFieldLive(field));
        });
    }

    storeFormRules(form) {
        const formRules = new Map();

        form.querySelectorAll('[data-validate]').forEach(field => {
            const fieldRules = field.dataset.validate.split('|').map(rule => {
                const [name, params] = rule.split(':');
                return { name, params };
            });
            formRules.set(field.name, fieldRules);
        });

        this.rules.set(form, formRules);
    }

    async handleFormSubmit(e) {
        const form = e.target;
        const isValid = await this.validateForm(form);

        if (!isValid) {
            e.preventDefault();
            this.scrollToFirstError(form);
        }
    }

    async validateForm(form) {
        const formRules = this.rules.get(form);
        if (!formRules) return true;

        let isValid = true;
        const validations = [];

        for (const [fieldName, rules] of formRules) {
            const field = form.querySelector(`[name="${fieldName}"]`);
            validations.push(this.validateField(field));
        }

        const results = await Promise.all(validations);
        return results.every(result => result);
    }

    async validateField(field) {
        const form = field.closest('form');
        const formRules = this.rules.get(form);
        if (!formRules) return true;

        const fieldRules = formRules.get(field.name);
        if (!fieldRules) return true;

        const value = this.getFieldValue(field);
        const errors = [];

        for (const rule of fieldRules) {
            const validator = this.customValidators.get(rule.name);
            if (validator) {
                const isValid = await Promise.resolve(validator.validate(value, rule.params));
                if (!isValid) {
                    errors.push(validator.message(rule.params));
                }
            }
        }

        this.updateFieldValidation(field, errors);
        return errors.length === 0;
    }

    validateFieldLive(field) {
        if (field.dataset.validateLive === 'true') {
            this.validateField(field);
        }
    }

    getFieldValue(field) {
        if (field.type === 'checkbox') {
            return field.checked;
        } else if (field.type === 'radio') {
            const checked = field.closest('form')
                .querySelector(`input[name="${field.name}"]:checked`);
            return checked ? checked.value : '';
        } else if (field.type === 'file') {
            return field.files;
        }
        return field.value;
    }

    updateFieldValidation(field, errors) {
        // Remove existing validation classes and messages
        field.classList.remove('is-valid', 'is-invalid');
        const container = field.closest('.form-group') || field.parentElement;
        container.querySelectorAll('.invalid-feedback').forEach(el => el.remove());

        if (errors.length > 0) {
            // Add error class and messages
            field.classList.add('is-invalid');
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.innerHTML = errors.join('<br>');
            container.appendChild(feedback);
        } else {
            // Add success class
            field.classList.add('is-valid');
        }
    }

    scrollToFirstError(form) {
        const firstError = form.querySelector('.is-invalid');
        if (firstError) {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

// Initialize validation handler
const validationHandler = new ValidationHandler();
export default validationHandler;
