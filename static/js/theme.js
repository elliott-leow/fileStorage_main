/**
 * Theme toggle. The pre-paint inline <script> in <head> already applied the
 * correct class (dark = Catppuccin Mocha is the default); this just wires the
 * toggle button and keeps the icon in sync.
 */
const ThemeManager = {
    init() {
        this.toggle = document.getElementById('theme-toggle');
        this.icon = document.getElementById('theme-icon');
        this.root = document.documentElement;
        this.syncIcon();
        if (this.toggle) {
            this.toggle.addEventListener('click', () => {
                this.setDark(!this.root.classList.contains('dark'));
            });
        }
    },

    syncIcon() {
        if (this.icon) this.icon.textContent = this.root.classList.contains('dark') ? '☀️' : '🌙';
    },

    setDark(isDark) {
        this.root.classList.toggle('dark', isDark);
        try { localStorage.setItem('theme', isDark ? 'dark' : 'light'); } catch (e) {}
        this.syncIcon();
    },
};

document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
