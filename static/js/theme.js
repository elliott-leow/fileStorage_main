/**
 * Theme management module
 */

const ThemeManager = {
    init() {
        this.themeToggle = document.getElementById('theme-toggle');
        this.themeIcon = document.getElementById('theme-icon');
        this.docElement = document.documentElement;
        
        // Load saved theme or detect preference
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.setTheme(savedTheme === 'dark' || (!savedTheme && prefersDark));
        
        // Attach event listener
        if (this.themeToggle) {
            this.themeToggle.addEventListener('click', () => {
                this.setTheme(!this.docElement.classList.contains('dark'));
            });
        }
    },
    
    setTheme(isDark) {
        if (isDark) {
            this.docElement.classList.add('dark');
            if (this.themeIcon) this.themeIcon.textContent = '☀️';
            localStorage.setItem('theme', 'dark');
        } else {
            this.docElement.classList.remove('dark');
            if (this.themeIcon) this.themeIcon.textContent = '🌙';
            localStorage.setItem('theme', 'light');
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => ThemeManager.init());


