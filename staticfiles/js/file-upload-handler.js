// static/js/file-upload-handler.js

class FileUploadHandler {
    constructor() {
        this.dropZones = new Map();
        this.activeUploads = new Map();
        this.maxFileSize = 50 * 1024 * 1024; // 50MB
        this.allowedTypes = new Set([
            'image/jpeg',
            'image/png',
            'image/gif',
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ]);

        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeDropZones();
        });
    }

    initializeDropZones() {
        document.querySelectorAll('[data-upload-zone]').forEach(zone => {
            this.setupDropZone(zone);
        });
    }

    setupDropZone(zone) {
        const config = {
            url: zone.dataset.uploadUrl,
            maxFiles: parseInt(zone.dataset.maxFiles) || 1,
            maxFileSize: parseInt(zone.dataset.maxSize) || this.maxFileSize,
            allowedTypes: zone.dataset.allowedTypes ?
                zone.dataset.allowedTypes.split(',') :
                Array.from(this.allowedTypes),
            autoProcess: zone.dataset.autoProcess !== 'false',
            multiple: zone.dataset.multiple === 'true'
        };

        this.dropZones.set(zone.id, { element: zone, config });

        this.setupDropZoneListeners(zone);
        this.createDropZoneInterface(zone);
    }

    setupDropZoneListeners(zone) {
        zone.addEventListener('dragenter', (e) => this.handleDragEnter(e));
        zone.addEventListener('dragover', (e) => this.handleDragOver(e));
        zone.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        zone.addEventListener('drop', (e) => this.handleDrop(e));

        // File input handling
        const input = zone.querySelector('input[type="file"]');
        if (input) {
            input.addEventListener('change', (e) => this.handleFileSelect(e));
        }
    }

    createDropZoneInterface(zone) {
        const config = this.dropZones.get(zone.id).config;

        zone.innerHTML = `
            <div class="upload-zone-content">
                <i class="fas fa-cloud-upload-alt"></i>
                <p>Drag & drop files here or</p>
                <input type="file" class="file-input" ${config.multiple ? 'multiple' : ''}
                       accept="${config.allowedTypes.join(',')}">
                <button type="button" class="btn btn-primary select-files-btn">
                    Select Files
                </button>
                <p class="upload-zone-info">
                    Max file size: ${this.formatFileSize(config.maxFileSize)}<br>
                    Allowed types: ${config.allowedTypes.join(', ')}
                </p>
            </div>
            <div class="upload-preview"></div>
            <div class="upload-progress"></div>
        `;

        // Setup file input trigger
        const selectButton = zone.querySelector('.select-files-btn');
        const fileInput = zone.querySelector('.file-input');
        selectButton.addEventListener('click', () => fileInput.click());
    }

    handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        e.currentTarget.classList.add('dragover');
    }

    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
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

        const files = Array.from(e.dataTransfer.files);
        this.processFiles(zone, files);
    }

    handleFileSelect(e) {
        const input = e.currentTarget;
        const zone = input.closest('[data-upload-zone]');
        const files = Array.from(input.files);
        this.processFiles(zone, files);
    }

    processFiles(zone, files) {
        const config = this.dropZones.get(zone.id).config;
        const validFiles = files.filter(file => this.validateFile(file, config));

        if (validFiles.length !== files.length) {
            notificationSystem.warning('Some files were skipped due to invalid type or size');
        }

        if (validFiles.length > 0) {
            this.updatePreview(zone, validFiles);
            if (config.autoProcess) {
                this.uploadFiles(zone, validFiles);
            }
        }
    }

    validateFile(file, config) {
        if (file.size > config.maxFileSize) {
            notificationSystem.error(
                `File ${file.name} is too large. Maximum size is ${this.formatFileSize(config.maxFileSize)}`
            );
            return false;
        }

        if (!config.allowedTypes.includes(file.type)) {
            notificationSystem.error(`File type ${file.type} is not allowed`);
            return false;
        }

        return true;
    }

    updatePreview(zone, files) {
        const previewContainer = zone.querySelector('.upload-preview');
        files.forEach(file => {
            const preview = document.createElement('div');
            preview.className = 'file-preview';

            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    preview.innerHTML = `
                        <img src="${e.target.result}" alt="${file.name}">
                        <span class="file-name">${file.name}</span>
                        <button type="button" class="remove-file">&times;</button>
                    `;
                };
                reader.readAsDataURL(file);
            } else {
                preview.innerHTML = `
                    <i class="fas ${this.getFileIcon(file.type)}"></i>
                    <span class="file-name">${file.name}</span>
                    <button type="button" class="remove-file">&times;</button>
                `;
            }

            preview.querySelector('.remove-file').addEventListener('click', () => {
                preview.remove();
            });

            previewContainer.appendChild(preview);
        });
    }

    async uploadFiles(zone, files) {
        const config = this.dropZones.get(zone.id).config;
        const progressContainer = zone.querySelector('.upload-progress');

        for (const file of files) {
            const formData = new FormData();
            formData.append('file', file);

            try {
                const progress = this.createProgressBar(progressContainer, file.name);

                const response = await fetch(config.url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': crmUtils.TOKEN
                    },
                    body: formData,
                    onUploadProgress: (e) => {
                        const percent = (e.loaded * 100) / e.total;
                        this.updateProgress(progress, percent);
                    }
                });

                if (!response.ok) throw new Error('Upload failed');

                const result = await response.json();
                this.handleUploadSuccess(zone, result, progress);
            } catch (error) {
                console.error('Upload error:', error);
                notificationSystem.error(`Failed to upload ${file.name}`);
            }
        }
    }

    createProgressBar(container, fileName) {
        const progress = document.createElement('div');
        progress.className = 'upload-progress-item';
        progress.innerHTML = `
            <div class="progress-info">
                <span class="filename">${fileName}</span>
                <span class="percent">0%</span>
            </div>
            <div class="progress">
                <div class="progress-bar" role="progressbar" style="width: 0%"></div>
            </div>
        `;
        container.appendChild(progress);
        return progress;
    }

    updateProgress(progressElement, percent) {
        const bar = progressElement.querySelector('.progress-bar');
        const percentText = progressElement.querySelector('.percent');

        bar.style.width = `${percent}%`;
        percentText.textContent = `${Math.round(percent)}%`;
    }

    handleUploadSuccess(zone, result, progressElement) {
        progressElement.classList.add('upload-complete');
        setTimeout(() => progressElement.remove(), 2000);

        // Trigger success event
        zone.dispatchEvent(new CustomEvent('uploadComplete', {
            detail: result
        }));
    }

    getFileIcon(fileType) {
        const icons = {
            'application/pdf': 'fa-file-pdf',
            'application/msword': 'fa-file-word',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'fa-file-word',
            'application/vnd.ms-excel': 'fa-file-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'fa-file-excel',
            'image': 'fa-file-image'
        };

        return icons[fileType] || icons[fileType.split('/')[0]] || 'fa-file';
    }

    formatFileSize(bytes) {
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;

        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }

        return `${size.toFixed(1)} ${units[unitIndex]}`;
    }
}

// Initialize file upload handler
const fileUploadHandler = new FileUploadHandler();
export default fileUploadHandler;
