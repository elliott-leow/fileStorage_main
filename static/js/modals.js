/**
 * Modal management utilities
 */

const ModalManager = {
    modals: {},
    
    /**
     * Register a modal for management
     */
    register(id, options = {}) {
        const modal = document.getElementById(id);
        if (!modal) return null;
        
        const config = {
            element: modal,
            onClose: options.onClose || null,
            closeOnEscape: options.closeOnEscape !== false,
            closeOnOverlay: options.closeOnOverlay !== false
        };
        
        this.modals[id] = config;
        
        // Setup overlay click handler
        if (config.closeOnOverlay) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hide(id);
                }
            });
        }
        
        return config;
    },
    
    /**
     * Show a modal
     */
    show(id) {
        const config = this.modals[id];
        if (config) {
            config.element.classList.add('active');
        }
    },
    
    /**
     * Hide a modal
     */
    hide(id) {
        const config = this.modals[id];
        if (config) {
            config.element.classList.remove('active');
            if (config.onClose) {
                config.onClose();
            }
        }
    },
    
    /**
     * Setup global escape key handler
     */
    setupEscapeHandler() {
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                Object.keys(this.modals).forEach(id => {
                    const config = this.modals[id];
                    if (config.closeOnEscape && config.element.classList.contains('active')) {
                        this.hide(id);
                    }
                });
            }
        });
    }
};

/**
 * Confirmation dialog utility
 */
const ConfirmDialog = {
    show(title, message, onConfirm, onCancel) {
        const modal = document.getElementById('confirmDeleteModal');
        const titleEl = modal.querySelector('h3');
        const textEl = document.getElementById('confirmDeleteText');
        const confirmBtn = document.getElementById('confirmDeleteConfirmBtn');
        const cancelBtn = document.getElementById('confirmDeleteCancelBtn');
        
        if (titleEl) titleEl.textContent = title;
        if (textEl) textEl.textContent = message;
        
        // Clear previous handlers
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        
        newConfirmBtn.addEventListener('click', () => {
            ModalManager.hide('confirmDeleteModal');
            if (onConfirm) onConfirm();
        });
        
        newCancelBtn.addEventListener('click', () => {
            ModalManager.hide('confirmDeleteModal');
            if (onCancel) onCancel();
        });
        
        ModalManager.show('confirmDeleteModal');
    }
};

// Initialize escape handler on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    ModalManager.setupEscapeHandler();
});


