// static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Task Status Updates
    const taskStatusButtons = document.querySelectorAll('.task-status-btn');
    taskStatusButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const taskId = this.dataset.taskId;
            const status = this.dataset.status;
            updateTaskStatus(taskId, status);
        });
    });

    // Meeting Type Toggle
    const meetingTypeSelect = document.getElementById('id_meeting_type');
    const zoomSettingsDiv = document.getElementById('zoomSettings');

    if (meetingTypeSelect && zoomSettingsDiv) {
        meetingTypeSelect.addEventListener('change', function() {
            if (this.value === 'zoom') {
                zoomSettingsDiv.style.display = 'block';
            } else {
                zoomSettingsDiv.style.display = 'none';
            }
        });
    }

    // Search Form Enhancement
    const searchForm = document.querySelector('.search-form');
    if (searchForm) {
        const searchInput = searchForm.querySelector('input[type="search"]');
        let timeoutId;

        searchInput.addEventListener('input', function() {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                searchForm.submit();
            }, 500);
        });
    }

    // Dynamic Form Fields
    function setupDynamicFields() {
        const customerSelect = document.getElementById('id_customer');
        const leadSelect = document.getElementById('id_lead');

        if (customerSelect && leadSelect) {
            customerSelect.addEventListener('change', function() {
                if (this.value) {
                    leadSelect.value = '';
                    leadSelect.disabled = true;
                } else {
                    leadSelect.disabled = false;
                }
            });

            leadSelect.addEventListener('change', function() {
                if (this.value) {
                    customerSelect.value = '';
                    customerSelect.disabled = true;
                } else {
                    customerSelect.disabled = false;
                }
            });
        }
    }

    // Phone Number Formatting
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            let x = e.target.value.replace(/\D/g, '').match(/(\d{0,3})(\d{0,3})(\d{0,4})/);
            e.target.value = !x[2] ? x[1] : '(' + x[1] + ') ' + x[2] + (x[3] ? '-' + x[3] : '');
        });
    });

    // Form Validation Enhancement
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Ajax Functions
    function updateTaskStatus(taskId, status) {
        fetch(`/tasks/${taskId}/status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ status: status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Error updating task status');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error updating task status');
        });
    }

    // Utility Functions
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Initialize dynamic fields
    setupDynamicFields();
});
