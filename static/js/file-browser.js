/**
 * File browser main functionality
 */

const FileBrowser = {
    config: {},
    
    /**
     * Initialize the file browser
     */
    init(config) {
        this.config = config;
        this.setupSearchForm();
        this.setupAccessKeyModal();
        this.setupDeleteMode();
        this.setupHiddenToggle();
        this.setupViewHiddenModal();
        this.setupCreateFolderModal();
        this.setupUploadFileModal();
    },
    
    /**
     * Setup search form handling
     */
    setupSearchForm() {
        const searchForm = document.getElementById('search-form');
        const searchInput = document.getElementById('search');
        const smartSearchInput = document.getElementById('smart-search');
        const recursiveCheckbox = document.getElementById('recursive');
        
        if (!searchForm) return;
        
        searchForm.addEventListener('submit', (event) => {
            event.preventDefault();
            const submitter = event.submitter;
            const isSmartSubmit = submitter?.name === 'submit_smart';
            const isFilterSubmit = submitter?.name === 'submit_filter';
            const filenameTerm = searchInput?.value.trim() || '';
            const smartTerm = smartSearchInput?.value.trim() || '';
            const isRecursive = recursiveCheckbox?.checked;
            
            const params = new URLSearchParams();
            let navigationTarget = window.location.pathname;
            
            if (this.config.semanticSearchEnabled && smartTerm && (isSmartSubmit || !isFilterSubmit)) {
                params.set('smart_query', smartTerm);
            } else {
                if (filenameTerm) params.set('search', filenameTerm);
                params.set('recursive', isRecursive ? 'true' : 'false');
            }
            
            if (!filenameTerm && !smartTerm && !isSmartSubmit && !isFilterSubmit) {
                window.location.href = navigationTarget;
                return;
            }
            
            const paramString = params.toString();
            const finalUrl = navigationTarget.replace(/\/$/, '') + '/' + (paramString ? '?' + paramString : '');
            window.location.href = finalUrl;
        });
    },
    
    /**
     * Setup access key modal for protected folders
     */
    setupAccessKeyModal() {
        const fileList = document.getElementById('file-list');
        const modal = document.getElementById('accessKeyModal');
        const modalKeyInput = document.getElementById('modalKeyInput');
        const modalError = document.getElementById('modalError');
        const modalCancelBtn = document.getElementById('modalCancelBtn');
        const modalSubmitBtn = document.getElementById('modalSubmitBtn');
        const modalPathLabel = document.getElementById('modalPathLabel');
        
        if (!fileList || !modal) return;
        
        let targetPathForModal = null;
        
        const showModal = (targetPath, folderName) => {
            targetPathForModal = targetPath;
            if (modalPathLabel) {
                try {
                    modalPathLabel.textContent = `For folder: ${decodeURIComponent(folderName)}`;
                } catch (e) {
                    modalPathLabel.textContent = `For folder: ${folderName}`;
                }
            }
            if (modalKeyInput) modalKeyInput.value = '';
            if (modalError) modalError.textContent = '';
            ModalManager.show('accessKeyModal');
            if (modalKeyInput) modalKeyInput.focus();
        };
        
        const hideModal = () => {
            ModalManager.hide('accessKeyModal');
            targetPathForModal = null;
        };
        
        // Register modal
        ModalManager.register('accessKeyModal', { onClose: () => { targetPathForModal = null; } });
        
        // Click handler for protected folder links
        fileList.addEventListener('click', (event) => {
            const link = event.target.closest('a.protected-folder-link');
            const listItem = link ? link.closest('li[data-protected="true"]') : null;
            
            if (link && listItem) {
                event.preventDefault();
                const targetHref = link.getAttribute('href');
                const folderName = link.querySelector('.folder-name')?.textContent.trim() || targetHref;
                showModal(targetHref, folderName);
            }
        });
        
        if (modalCancelBtn) modalCancelBtn.addEventListener('click', hideModal);
        
        // Submit handler
        if (modalSubmitBtn) {
            modalSubmitBtn.addEventListener('click', async () => {
                const enteredKey = modalKeyInput?.value;
                if (!targetPathForModal || !enteredKey) return;
                
                modalSubmitBtn.disabled = true;
                if (modalError) modalError.textContent = '';
                
                try {
                    const response = await fetch('/validate-key', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: targetPathForModal, key: enteredKey })
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok && result.status === 'success') {
                        hideModal();
                        window.location.href = targetPathForModal;
                    } else {
                        if (modalError) modalError.textContent = result.message || 'Invalid key.';
                        if (modalKeyInput) {
                            modalKeyInput.focus();
                            modalKeyInput.select();
                        }
                    }
                } catch (error) {
                    if (modalError) modalError.textContent = 'Network error.';
                } finally {
                    modalSubmitBtn.disabled = false;
                }
            });
        }
        
        // Enter key support
        if (modalKeyInput) {
            modalKeyInput.addEventListener('keypress', (event) => {
                if (event.key === 'Enter' && modalSubmitBtn && !modalSubmitBtn.disabled) {
                    event.preventDefault();
                    modalSubmitBtn.click();
                }
            });
        }
    },
    
    /**
     * Setup delete mode functionality
     */
    setupDeleteMode() {
        if (!this.config.deleteKeyConfigured) return;
        
        const deleteModeBtn = document.getElementById('delete-mode-btn');
        const deleteModalKeyInput = document.getElementById('deleteModalKeyInput');
        const deleteModalError = document.getElementById('deleteModalError');
        const deleteModalSubmitBtn = document.getElementById('deleteModalSubmitBtn');
        const deleteModalCancelBtn = document.getElementById('deleteModalCancelBtn');
        const cancelDeleteModeBtn = document.getElementById('cancel-delete-mode-btn');
        const deleteSelectedBtn = document.getElementById('delete-selected-btn');
        const fileListCheckboxes = document.querySelectorAll('.delete-checkbox');
        const deleteResultCloseBtn = document.getElementById('deleteResultCloseBtn');
        
        let enteredDeleteKey = null;
        
        // Register modals
        ModalManager.register('deleteKeyModal');
        ModalManager.register('confirmDeleteModal');
        ModalManager.register('deleteResultModal');
        
        const enterDeleteMode = (validKey) => {
            enteredDeleteKey = validKey;
            document.body.classList.add('delete-mode');
            ModalManager.hide('deleteKeyModal');
            checkAnyCheckboxSelected();
        };
        
        const exitDeleteMode = () => {
            enteredDeleteKey = null;
            document.body.classList.remove('delete-mode');
            fileListCheckboxes.forEach(cb => cb.checked = false);
        };
        
        const checkAnyCheckboxSelected = () => {
            const anyChecked = Array.from(fileListCheckboxes).some(cb => cb.checked);
            if (deleteSelectedBtn) deleteSelectedBtn.disabled = !anyChecked;
        };
        
        if (deleteModeBtn) {
            deleteModeBtn.addEventListener('click', () => ModalManager.show('deleteKeyModal'));
        }
        
        if (deleteModalCancelBtn) {
            deleteModalCancelBtn.addEventListener('click', () => ModalManager.hide('deleteKeyModal'));
        }
        
        if (deleteModalSubmitBtn) {
            deleteModalSubmitBtn.addEventListener('click', () => {
                const keyAttempt = deleteModalKeyInput?.value;
                if (deleteModalError) deleteModalError.textContent = '';
                
                if (keyAttempt && keyAttempt.length > 0) {
                    enterDeleteMode(keyAttempt);
                } else {
                    if (deleteModalError) deleteModalError.textContent = 'Key cannot be empty.';
                }
            });
        }
        
        if (deleteModalKeyInput) {
            deleteModalKeyInput.addEventListener('keypress', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    deleteModalSubmitBtn?.click();
                }
            });
        }
        
        if (cancelDeleteModeBtn) {
            cancelDeleteModeBtn.addEventListener('click', exitDeleteMode);
        }
        
        fileListCheckboxes.forEach(cb => {
            cb.addEventListener('change', checkAnyCheckboxSelected);
        });
        
        if (deleteSelectedBtn) {
            deleteSelectedBtn.addEventListener('click', () => {
                const itemsToDelete = Array.from(fileListCheckboxes)
                    .filter(cb => cb.checked)
                    .map(cb => cb.value);
                
                if (itemsToDelete.length === 0) return;
                if (!enteredDeleteKey) return;
                
                ConfirmDialog.show(
                    'Confirm Deletion',
                    `Are you sure you want to delete ${itemsToDelete.length} item(s)? This cannot be undone.`,
                    () => this.performDelete(itemsToDelete, enteredDeleteKey)
                );
            });
        }
        
        if (deleteResultCloseBtn) {
            deleteResultCloseBtn.addEventListener('click', () => {
                ModalManager.hide('deleteResultModal');
                location.reload();
            });
        }
    },
    
    /**
     * Perform delete operation
     */
    async performDelete(itemsToDelete, deleteKey) {
        const deleteResultTitle = document.getElementById('deleteResultTitle');
        const deleteResultMessage = document.getElementById('deleteResultMessage');
        
        try {
            const response = await fetch('/api/delete-items', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Delete-Key': deleteKey
                },
                body: JSON.stringify({ items_to_delete: itemsToDelete })
            });
            
            const result = await response.json();
            
            let resultHTML = `<p>Success: <strong>${result.success_count || 0}</strong>, Failed: <strong>${result.fail_count || 0}</strong></p>`;
            if (result.errors && result.errors.length > 0) {
                resultHTML += '<p class="mt-2 font-medium">Errors:</p><ul class="list-disc list-inside text-xs">';
                result.errors.forEach(err => {
                    resultHTML += `<li><code>${err.path}</code>: ${err.error}</li>`;
                });
                resultHTML += '</ul>';
            }
            
            if (deleteResultTitle) {
                deleteResultTitle.textContent = result.fail_count > 0 ? 'Deletion Complete (with errors)' : 'Deletion Successful';
            }
            if (deleteResultMessage) {
                deleteResultMessage.innerHTML = resultHTML;
            }
            
            ModalManager.show('deleteResultModal');
        } catch (error) {
            if (deleteResultTitle) deleteResultTitle.textContent = 'Deletion Error';
            if (deleteResultMessage) deleteResultMessage.textContent = `Error: ${error.message}`;
            ModalManager.show('deleteResultModal');
        }
    },
    
    /**
     * Setup hidden folder toggle
     */
    setupHiddenToggle() {
        if (!this.config.hiddenKeyConfigured) return;
        
        const hiddenToggle = document.getElementById('hidden-toggle');
        const hiddenModalKeyInput = document.getElementById('hiddenModalKeyInput');
        const hiddenModalError = document.getElementById('hiddenModalError');
        const hiddenModalCancelBtn = document.getElementById('hiddenModalCancelBtn');
        const hiddenModalConfirmBtn = document.getElementById('hiddenModalConfirmBtn');
        const hiddenModalActionText = document.getElementById('hiddenModalActionText');
        
        if (!hiddenToggle) return;
        
        ModalManager.register('hiddenKeyModal', {
            onClose: () => {
                // Revert checkbox state on cancel
                hiddenToggle.checked = this.config.isCurrentPathHidden;
            }
        });
        
        hiddenToggle.addEventListener('change', (event) => {
            const isChecked = event.target.checked;
            const actionText = isChecked
                ? `This will hide the folder '/${this.config.currentPath}' from listings.`
                : `This will make the folder '/${this.config.currentPath}' visible again.`;
            
            if (hiddenModalActionText) hiddenModalActionText.textContent = actionText + ' Enter the key to confirm.';
            if (hiddenModalKeyInput) hiddenModalKeyInput.value = '';
            if (hiddenModalError) hiddenModalError.textContent = '';
            ModalManager.show('hiddenKeyModal');
            if (hiddenModalKeyInput) hiddenModalKeyInput.focus();
        });
        
        if (hiddenModalCancelBtn) {
            hiddenModalCancelBtn.addEventListener('click', () => ModalManager.hide('hiddenKeyModal'));
        }
        
        if (hiddenModalConfirmBtn) {
            hiddenModalConfirmBtn.addEventListener('click', async () => {
                const key = hiddenModalKeyInput?.value;
                const shouldHide = hiddenToggle.checked;
                
                if (!key) {
                    if (hiddenModalError) hiddenModalError.textContent = 'Key required.';
                    return;
                }
                
                hiddenModalConfirmBtn.disabled = true;
                
                try {
                    const response = await fetch('/api/toggle-hidden', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            path: this.config.currentPath,
                            key: key,
                            hide: shouldHide
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(result.error || 'Request failed');
                    }
                    
                    window.location.href = this.config.parentUrl || '/';
                } catch (error) {
                    if (hiddenModalError) hiddenModalError.textContent = error.message;
                    hiddenModalConfirmBtn.disabled = false;
                }
            });
        }
        
        if (hiddenModalKeyInput) {
            hiddenModalKeyInput.addEventListener('keypress', (event) => {
                if (event.key === 'Enter' && hiddenModalConfirmBtn && !hiddenModalConfirmBtn.disabled) {
                    event.preventDefault();
                    hiddenModalConfirmBtn.click();
                }
            });
        }
    },
    
    /**
     * Setup view hidden folders modal
     */
    setupViewHiddenModal() {
        if (!this.config.hiddenKeyConfigured) return;
        
        const viewHiddenBtn = document.getElementById('view-hidden-btn');
        const viewHiddenKeyInput = document.getElementById('viewHiddenKeyInput');
        const viewHiddenError = document.getElementById('viewHiddenError');
        const viewHiddenCancelBtn = document.getElementById('viewHiddenCancelBtn');
        const viewHiddenConfirmBtn = document.getElementById('viewHiddenConfirmBtn');
        const viewHiddenTitle = document.getElementById('viewHiddenTitle');
        const viewHiddenText = document.getElementById('viewHiddenText');
        
        if (!viewHiddenBtn) return;
        
        ModalManager.register('viewHiddenModal');
        
        viewHiddenBtn.addEventListener('click', () => {
            if (this.config.showHiddenFiles) {
                if (viewHiddenTitle) viewHiddenTitle.textContent = 'Hide Hidden Folders';
                if (viewHiddenText) viewHiddenText.textContent = 'Enter password to hide hidden folders again.';
            } else {
                if (viewHiddenTitle) viewHiddenTitle.textContent = 'View Hidden Folders';
                if (viewHiddenText) viewHiddenText.textContent = 'Enter password to see all hidden folders.';
            }
            if (viewHiddenKeyInput) viewHiddenKeyInput.value = '';
            if (viewHiddenError) viewHiddenError.textContent = '';
            ModalManager.show('viewHiddenModal');
            if (viewHiddenKeyInput) viewHiddenKeyInput.focus();
        });
        
        if (viewHiddenCancelBtn) {
            viewHiddenCancelBtn.addEventListener('click', () => ModalManager.hide('viewHiddenModal'));
        }
        
        if (viewHiddenConfirmBtn) {
            viewHiddenConfirmBtn.addEventListener('click', async () => {
                const key = viewHiddenKeyInput?.value;
                if (!key) {
                    if (viewHiddenError) viewHiddenError.textContent = 'Password required.';
                    return;
                }
                
                viewHiddenConfirmBtn.disabled = true;
                
                try {
                    const response = await fetch('/api/toggle-view-hidden', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ key: key })
                    });
                    
                    const result = await response.json();
                    if (response.ok) {
                        location.reload();
                    } else {
                        if (viewHiddenError) viewHiddenError.textContent = result.error || 'Failed.';
                    }
                } catch (e) {
                    if (viewHiddenError) viewHiddenError.textContent = 'Network error.';
                } finally {
                    viewHiddenConfirmBtn.disabled = false;
                }
            });
        }
        
        if (viewHiddenKeyInput) {
            viewHiddenKeyInput.addEventListener('keypress', (event) => {
                if (event.key === 'Enter' && viewHiddenConfirmBtn && !viewHiddenConfirmBtn.disabled) {
                    event.preventDefault();
                    viewHiddenConfirmBtn.click();
                }
            });
        }
    },
    
    /**
     * Setup create folder modal
     */
    setupCreateFolderModal() {
        const createFolderBtn = document.getElementById('create-folder-btn');
        const newFolderName = document.getElementById('newFolderName');
        const createFolderKey = document.getElementById('createFolderKey');
        const createFolderError = document.getElementById('createFolderError');
        const createFolderCancelBtn = document.getElementById('createFolderCancelBtn');
        const createFolderConfirmBtn = document.getElementById('createFolderConfirmBtn');
        const enableFolderProtection = document.getElementById('enableFolderProtection');
        const folderProtectionPasswordContainer = document.getElementById('folderProtectionPasswordContainer');
        const folderProtectionPassword = document.getElementById('folderProtectionPassword');
        
        if (!createFolderBtn) return;
        
        ModalManager.register('createFolderModal');
        
        createFolderBtn.addEventListener('click', () => {
            if (newFolderName) newFolderName.value = '';
            if (createFolderKey) createFolderKey.value = '';
            if (createFolderError) createFolderError.textContent = '';
            if (enableFolderProtection) enableFolderProtection.checked = false;
            if (folderProtectionPassword) folderProtectionPassword.value = '';
            if (folderProtectionPasswordContainer) folderProtectionPasswordContainer.classList.add('hidden');
            ModalManager.show('createFolderModal');
            if (newFolderName) newFolderName.focus();
        });
        
        if (createFolderCancelBtn) {
            createFolderCancelBtn.addEventListener('click', () => ModalManager.hide('createFolderModal'));
        }
        
        if (enableFolderProtection && folderProtectionPasswordContainer) {
            enableFolderProtection.addEventListener('change', () => {
                if (enableFolderProtection.checked) {
                    folderProtectionPasswordContainer.classList.remove('hidden');
                    if (folderProtectionPassword) folderProtectionPassword.focus();
                } else {
                    folderProtectionPasswordContainer.classList.add('hidden');
                    if (folderProtectionPassword) folderProtectionPassword.value = '';
                }
            });
        }
        
        if (createFolderConfirmBtn) {
            createFolderConfirmBtn.addEventListener('click', async () => {
                const name = newFolderName?.value.trim();
                const key = createFolderKey?.value;
                
                if (!name || !key) {
                    if (createFolderError) createFolderError.textContent = 'Name and Password required.';
                    return;
                }
                
                const protectFolder = enableFolderProtection?.checked;
                const protectionPwd = protectFolder ? folderProtectionPassword?.value : null;
                
                if (protectFolder && !protectionPwd) {
                    if (createFolderError) createFolderError.textContent = 'Protection password required.';
                    return;
                }
                
                createFolderConfirmBtn.disabled = true;
                if (createFolderError) createFolderError.textContent = '';
                
                try {
                    const response = await fetch('/api/create-folder', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            parent_path: this.config.currentPath,
                            folder_name: name,
                            key: key,
                            protection_password: protectionPwd
                        })
                    });
                    
                    const result = await response.json();
                    if (response.ok) {
                        location.reload();
                    } else {
                        if (createFolderError) createFolderError.textContent = result.error || 'Failed.';
                    }
                } catch (e) {
                    if (createFolderError) createFolderError.textContent = 'Network error.';
                } finally {
                    createFolderConfirmBtn.disabled = false;
                }
            });
        }
        
        [createFolderKey, folderProtectionPassword].forEach(input => {
            if (input) {
                input.addEventListener('keypress', (event) => {
                    if (event.key === 'Enter' && createFolderConfirmBtn && !createFolderConfirmBtn.disabled) {
                        event.preventDefault();
                        createFolderConfirmBtn.click();
                    }
                });
            }
        });
    },
    
    /**
     * Setup upload file modal
     */
    setupUploadFileModal() {
        const uploadFileBtn = document.getElementById('upload-file-btn');
        const uploadFileInput = document.getElementById('uploadFileInput');
        const uploadFileInputLabel = document.getElementById('uploadFileInputLabel');
        const uploadModeFiles = document.getElementById('uploadModeFiles');
        const uploadModeFolder = document.getElementById('uploadModeFolder');
        const uploadTargetFolder = document.getElementById('uploadTargetFolder');
        const uploadFileKey = document.getElementById('uploadFileKey');
        const uploadFileError = document.getElementById('uploadFileError');
        const uploadFileCancelBtn = document.getElementById('uploadFileCancelBtn');
        const uploadFileConfirmBtn = document.getElementById('uploadFileConfirmBtn');
        const folderProtectionContainer = document.getElementById('folderProtectionContainer');
        const enableProtection = document.getElementById('enableProtection');
        const protectionPasswordContainer = document.getElementById('protectionPasswordContainer');
        const protectionPassword = document.getElementById('protectionPassword');
        
        if (!uploadFileBtn) return;
        
        ModalManager.register('uploadFileModal');
        
        const toggleUploadMode = () => {
            const isFolderMode = uploadModeFolder?.checked;
            if (uploadFileInput) {
                if (isFolderMode) {
                    uploadFileInput.removeAttribute('multiple');
                    uploadFileInput.setAttribute('webkitdirectory', 'webkitdirectory');
                    uploadFileInput.setAttribute('directory', 'directory');
                } else {
                    uploadFileInput.removeAttribute('webkitdirectory');
                    uploadFileInput.removeAttribute('directory');
                    uploadFileInput.setAttribute('multiple', 'multiple');
                }
            }
            if (uploadFileInputLabel) {
                uploadFileInputLabel.textContent = isFolderMode ? 'Select Folder' : 'Select File(s)';
            }
            if (folderProtectionContainer) {
                if (isFolderMode) {
                    folderProtectionContainer.classList.remove('hidden');
                } else {
                    folderProtectionContainer.classList.add('hidden');
                    if (enableProtection) enableProtection.checked = false;
                    if (protectionPasswordContainer) protectionPasswordContainer.classList.add('hidden');
                    if (protectionPassword) protectionPassword.value = '';
                }
            }
        };
        
        if (uploadModeFiles) uploadModeFiles.addEventListener('change', toggleUploadMode);
        if (uploadModeFolder) uploadModeFolder.addEventListener('change', toggleUploadMode);
        
        if (enableProtection && protectionPasswordContainer) {
            enableProtection.addEventListener('change', () => {
                if (enableProtection.checked) {
                    protectionPasswordContainer.classList.remove('hidden');
                    if (protectionPassword) protectionPassword.focus();
                } else {
                    protectionPasswordContainer.classList.add('hidden');
                    if (protectionPassword) protectionPassword.value = '';
                }
            });
        }
        
        uploadFileBtn.addEventListener('click', () => {
            if (uploadFileInput) uploadFileInput.value = '';
            if (uploadFileKey) uploadFileKey.value = '';
            if (uploadFileError) uploadFileError.textContent = '';
            if (enableProtection) enableProtection.checked = false;
            if (protectionPasswordContainer) protectionPasswordContainer.classList.add('hidden');
            if (protectionPassword) protectionPassword.value = '';
            if (uploadModeFiles) uploadModeFiles.checked = true;
            if (uploadModeFolder) uploadModeFolder.checked = false;
            toggleUploadMode();
            if (uploadTargetFolder) uploadTargetFolder.value = this.config.currentPath;
            ModalManager.show('uploadFileModal');
        });
        
        if (uploadFileCancelBtn) {
            uploadFileCancelBtn.addEventListener('click', () => ModalManager.hide('uploadFileModal'));
        }
        
        if (uploadFileConfirmBtn) {
            uploadFileConfirmBtn.addEventListener('click', () => this.performUpload());
        }
        
        [uploadFileKey, protectionPassword].forEach(input => {
            if (input) {
                input.addEventListener('keypress', (event) => {
                    if (event.key === 'Enter' && uploadFileConfirmBtn && !uploadFileConfirmBtn.disabled) {
                        event.preventDefault();
                        uploadFileConfirmBtn.click();
                    }
                });
            }
        });
    },
    
    /**
     * Format bytes to human readable string
     */
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
    },
    
    /**
     * Upload a single file with progress tracking using XMLHttpRequest
     */
    uploadFileWithProgress(file, url, key, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && onProgress) {
                    onProgress(e.loaded, e.total);
                }
            });
            
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve({ ok: true, status: xhr.status });
                } else {
                    resolve({ ok: false, status: xhr.status });
                }
            });
            
            xhr.addEventListener('error', () => {
                reject(new Error('Network error'));
            });
            
            xhr.addEventListener('abort', () => {
                reject(new Error('Upload aborted'));
            });
            
            xhr.open('POST', url);
            xhr.setRequestHeader('X-Upload-Key', key);
            xhr.send(file);
        });
    },
    
    /**
     * Update progress UI
     */
    updateProgressUI(currentFile, totalFiles, fileName, loaded, total, totalLoaded, grandTotal) {
        const progressContainer = document.getElementById('uploadProgressContainer');
        const progressBar = document.getElementById('uploadProgressBar');
        const progressPercent = document.getElementById('uploadProgressPercent');
        const progressBytes = document.getElementById('uploadProgressBytes');
        const progressLabel = document.getElementById('uploadProgressLabel');
        const progressFile = document.getElementById('uploadProgressFile');
        
        if (progressContainer) progressContainer.classList.remove('hidden');
        
        // Overall progress
        const overallPercent = grandTotal > 0 ? Math.round((totalLoaded / grandTotal) * 100) : 0;
        
        if (progressBar) progressBar.style.width = `${overallPercent}%`;
        if (progressPercent) progressPercent.textContent = `${overallPercent}%`;
        if (progressBytes) progressBytes.textContent = `${this.formatBytes(totalLoaded)} / ${this.formatBytes(grandTotal)}`;
        if (progressLabel) progressLabel.textContent = `Uploading: ${fileName}`;
        if (progressFile) progressFile.textContent = `File ${currentFile} of ${totalFiles}`;
    },
    
    /**
     * Perform file upload
     */
    async performUpload() {
        const uploadFileInput = document.getElementById('uploadFileInput');
        const uploadModeFolder = document.getElementById('uploadModeFolder');
        const uploadTargetFolder = document.getElementById('uploadTargetFolder');
        const uploadFileKey = document.getElementById('uploadFileKey');
        const uploadFileError = document.getElementById('uploadFileError');
        const uploadFileConfirmBtn = document.getElementById('uploadFileConfirmBtn');
        const uploadFileCancelBtn = document.getElementById('uploadFileCancelBtn');
        const enableProtection = document.getElementById('enableProtection');
        const protectionPassword = document.getElementById('protectionPassword');
        const progressContainer = document.getElementById('uploadProgressContainer');
        
        const files = uploadFileInput?.files;
        const key = uploadFileKey?.value;
        let targetPath = uploadTargetFolder?.value.trim() || this.config.currentPath;
        const isFolderMode = uploadModeFolder?.checked;
        
        targetPath = targetPath.replace(/^\/+|\/+$/g, '');
        
        if (!files || files.length === 0) {
            if (uploadFileError) uploadFileError.textContent = isFolderMode ? 'Select a folder.' : 'Select at least one file.';
            return;
        }
        if (!key) {
            if (uploadFileError) uploadFileError.textContent = 'Password required.';
            return;
        }
        
        const protectFolder = isFolderMode && enableProtection?.checked;
        const protectionPwd = protectFolder ? protectionPassword?.value : null;
        
        if (protectFolder && !protectionPwd) {
            if (uploadFileError) uploadFileError.textContent = 'Protection password required.';
            return;
        }
        
        // Disable buttons during upload
        if (uploadFileConfirmBtn) {
            uploadFileConfirmBtn.disabled = true;
            uploadFileConfirmBtn.textContent = 'Uploading...';
        }
        if (uploadFileCancelBtn) uploadFileCancelBtn.disabled = true;
        if (uploadFileError) {
            uploadFileError.textContent = '';
            uploadFileError.className = 'mt-2 text-sm text-red-600 dark:text-red-400 h-5';
        }
        
        // Calculate total size for progress
        let grandTotal = 0;
        for (let i = 0; i < files.length; i++) {
            grandTotal += files[i].size;
        }
        
        let successCount = 0;
        let failCount = 0;
        let totalLoaded = 0;
        let folderBasePath = null;
        
        if (isFolderMode && files.length > 0 && files[0].webkitRelativePath) {
            const firstPath = files[0].webkitRelativePath.replace(/\\/g, '/');
            const folderName = firstPath.split('/')[0];
            folderBasePath = targetPath ? `${targetPath}/${folderName}` : folderName;
        }
        
        // Show progress container
        if (progressContainer) progressContainer.classList.remove('hidden');
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            let relPath;
            
            if (isFolderMode && file.webkitRelativePath) {
                const relativePath = file.webkitRelativePath.replace(/\\/g, '/');
                relPath = targetPath ? `${targetPath}/${relativePath}` : relativePath;
            } else {
                relPath = targetPath ? `${targetPath}/${file.name}` : file.name;
            }
            
            const fileStartLoaded = totalLoaded;
            
            try {
                const result = await this.uploadFileWithProgress(
                    file,
                    `/upload/${relPath}`,
                    key,
                    (loaded, total) => {
                        // Update progress for this file
                        const currentTotalLoaded = fileStartLoaded + loaded;
                        this.updateProgressUI(
                            i + 1,
                            files.length,
                            file.name,
                            loaded,
                            total,
                            currentTotalLoaded,
                            grandTotal
                        );
                    }
                );
                
                if (result.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (e) {
                failCount++;
            }
            
            totalLoaded += file.size;
        }
        
        // Final progress update
        this.updateProgressUI(files.length, files.length, 'Complete', grandTotal, grandTotal, grandTotal, grandTotal);
        
        // Set protection if requested
        if (protectFolder && successCount > 0 && folderBasePath) {
            try {
                await fetch('/api/set-path-protection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: folderBasePath,
                        password: protectionPwd,
                        key: key
                    })
                });
            } catch (e) {
                console.warn('Failed to set folder protection');
            }
        }
        
        // Re-enable cancel button
        if (uploadFileCancelBtn) uploadFileCancelBtn.disabled = false;
        
        if (failCount === 0) {
            const normInitial = this.config.currentPath.replace(/^\/+|\/+$/g, '');
            if (targetPath === normInitial) {
                // Show success briefly before reload
                if (uploadFileError) {
                    uploadFileError.className = 'mt-2 text-sm text-green-600 dark:text-green-400 h-5';
                    uploadFileError.textContent = `Upload complete! ${successCount} file(s) uploaded.`;
                }
                setTimeout(() => location.reload(), 1000);
            } else {
                if (uploadFileError) {
                    uploadFileError.className = 'mt-2 text-sm text-green-600 dark:text-green-400 h-5';
                    uploadFileError.textContent = `Upload successful! ${successCount} file(s) uploaded.`;
                }
                setTimeout(() => {
                    ModalManager.hide('uploadFileModal');
                    if (uploadFileConfirmBtn) {
                        uploadFileConfirmBtn.disabled = false;
                        uploadFileConfirmBtn.textContent = 'Upload';
                    }
                    if (progressContainer) progressContainer.classList.add('hidden');
                }, 2000);
            }
        } else {
            if (uploadFileError) {
                uploadFileError.textContent = `Uploaded ${successCount}, failed ${failCount}.`;
            }
            if (uploadFileConfirmBtn) {
                uploadFileConfirmBtn.disabled = false;
                uploadFileConfirmBtn.textContent = 'Upload';
            }
        }
    }
};


