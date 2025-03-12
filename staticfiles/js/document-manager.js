// static/js/document-manager.js

class DocumentManager {
    constructor() {
        this.maxFileSize = 10 * 1024 * 1024; // 10MB
        this.allowedTypes = new Set([
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'image/jpeg',
            'image/png'
        ]);
        this.init();
    }

    init() {
        this.setupDropZones();
        this.setupFileInputs();
    }

    setupDropZones() {
        const dropZones = document.querySelectorAll('.dropzone');
        dropZones.forEach(zone => {
            zone.addEventListener('dragover', (e) => this.handleDragOver(e));
            zone.addEventListener('dragleave', (e) => this.handleDragLeave(e));
            zone.addEventListener('drop', (e) => this.handleDrop(e));
        });
    }

    setupFileInputs() {
        const fileInputs = document.querySelectorAll('.file-input');
        fileInputs.forEach(input => {
            input.addEventListener('change', (e) => this.handleFileSelect(e));
        });
    }

    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        e.currentTarget.classList.add('dragover');
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        e.currentTarget.classList.remove('dragover');
    }

    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        const zone = e.currentTarget;
        zone.classList.remove('dragover');

        const files = e.dataTransfer.files;
        this.processFiles(files, zone);
    }

    handleFileSelect(e) {
        const input = e.currentTarget;
        const files = input.files;
        this.processFiles(files, input.closest('.file-upload-container'));
    }

    async processFiles(files, container) {
        const fileList = Array.from(files);
        const validFiles = fileList.filter(file => this.validateFile(file));

        if (validFiles.length !== fileList.length) {
            crmUtils.showNotification('Some files were skipped due to invalid type or size', 'warning');
        }

        for (const file of validFiles) {
            await this.uploadFile(file, container);
        }
    }

    validateFile(file) {
        if (file.size > this.maxFileSize) {
            crmUtils.showNotification(`File ${file.name} is too large. Maximum size is 10MB`, 'error');
            return false;
        }

        if (!this.allowedTypes.has(file.type)) {
            crmUtils.showNotification(`File type ${file.type} is not allowed`, 'error');
            return false;
        }

        return true;
    }

    async uploadFile(file, container) {
        const formData = new FormData();
        formData.append('file', file);

        const progressBar = this.createProgressBar(container);

        try {
            const response = await fetch('/api/documents/upload/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': crmUtils.TOKEN
                },
                body: formData,
                onUploadProgress: (progressEvent) => {
                    const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                    this.updateProgressBar(progressBar, percentCompleted);
                }
            });

            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const result = await response.json();
            this.handleUploadSuccess(result, container);
        } catch (error) {
            console.error('Upload error:', error);
            this.handleUploadError(error, container);
        } finally {
            this.removeProgressBar(progressBar);
        }
    }

    createProgressBar(container) {
        const progressBar = document.createElement('div');
        progressBar.className = 'progress mt-2';
        progressBar.innerHTML = `
            <div class="progress-bar progress-bar-striped progress-bar-animated"
                 role="progressbar" style="width: 0%"
                 aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
            </div>
        `;
        container.appendChild(progressBar);
        return progressBar;
    }

    updateProgressBar(progressBar, percentage) {
        const bar = progressBar.querySelector('.progress-bar');
        bar.style.width = `${percentage}%`;
        bar.setAttribute('aria-valuenow', percentage);
    }

    removeProgressBar(progressBar) {
        setTimeout(() => {
            progressBar.remove();
        }, 1000);
    }

    handleUploadSuccess(result, container) {
        this.addFileToList(result, container);
        crmUtils.showNotification('File uploaded successfully', 'success');
    }

    handleUploadError(error, container) {
        crmUtils.showNotification('Failed to upload file', 'error');
    }

    addFileToList(fileData, container) {
        const fileList = container.querySelector('.file-list') || this.createFileList(container);
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item d-flex justify-content-between align-items-center p-2 border-bottom';
        fileItem.innerHTML = `
            <div class="file-info">
                <i class="fas ${this.getFileIcon(fileData.type)}"></i>
                <span class="ms-2">${fileData.name}</span>
            </div>
            <div class="file-actions">
                <button class="btn btn-sm btn-primary me-1" onclick="window.open('${fileData.url}')">
                    <i class="fas fa-download"></i>
                </button>
                <button class="btn btn-sm btn-danger" onclick="documentManager.deleteFile('${fileData.id}', this)">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        fileList.appendChild(fileItem);
    }

    createFileList(container) {
        const fileList = document.createElement('div');
        fileList.className = 'file-list mt-3';
        container.appendChild(fileList);
        return fileList;
    }

    getFileIcon(fileType) {
        const iconMap = {
            'application/pdf': 'fa-file-pdf',
            'application/msword': 'fa-file-word',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'fa-file-word',
            'application/vnd.ms-excel': 'fa-file-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'fa-file-excel',
            'image/jpeg': 'fa-file-image',
            'image/png': 'fa-file-image'
        };
        return iconMap[fileType] || 'fa-file';
    }

    async deleteFile(fileId, button) {
        if (!confirm('Are you sure you want to delete this file?')) {
            return;
        }

        try {
            const response = await fetch(`/api/documents/${fileId}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': crmUtils.TOKEN
                }
            });

            if (!response.ok) {
                throw new Error('Delete failed');
            }

            button.closest('.file-item').remove();
            crmUtils.showNotification('File deleted successfully', 'success');
        } catch (error) {
            console.error('Delete error:', error);
            crmUtils.showNotification('Failed to delete file', 'error');
        }
    }
}

// Initialize document manager
const documentManager = new DocumentManager();

// Export for module use
export default documentManager;
