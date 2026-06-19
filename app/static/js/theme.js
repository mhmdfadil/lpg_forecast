/* =====================================================================
   THEME SWITCHER — Light / Dark / System
   ===================================================================== */
(function () {
    const STORAGE_KEY = "lpg-theme";
    const root = document.documentElement;

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.themeBtn === theme);
        });
    }

    function initTheme() {
        const saved = localStorage.getItem(STORAGE_KEY) || "system";
        applyTheme(saved);
    }

    function setTheme(theme) {
        localStorage.setItem(STORAGE_KEY, theme);
        applyTheme(theme);
    }

    document.addEventListener("DOMContentLoaded", () => {
        initTheme();
        document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
            btn.addEventListener("click", () => setTheme(btn.dataset.themeBtn));
        });

        // Sidebar mobile toggle
        const hamburger = document.querySelector("[data-sidebar-toggle]");
        const sidebar = document.querySelector(".sidebar");
        const backdrop = document.querySelector(".sidebar-backdrop");
        if (hamburger && sidebar && backdrop) {
            const closeSidebar = () => {
                sidebar.classList.remove("is-open");
                backdrop.classList.remove("is-open");
            };
            hamburger.addEventListener("click", () => {
                sidebar.classList.toggle("is-open");
                backdrop.classList.toggle("is-open");
            });
            backdrop.addEventListener("click", closeSidebar);
        }

        // Auto-dismiss flash alerts
        document.querySelectorAll("[data-flash]").forEach((el) => {
            setTimeout(() => {
                el.style.transition = "opacity 400ms ease, transform 400ms ease";
                el.style.opacity = "0";
                el.style.transform = "translateY(-8px)";
                setTimeout(() => el.remove(), 420);
            }, 5200);
        });

        // Tabs
        document.querySelectorAll("[data-tabs]").forEach((tabGroup) => {
            const buttons = tabGroup.querySelectorAll(".tab-btn");
            const targetSelector = tabGroup.dataset.tabs;
            buttons.forEach((btn) => {
                btn.addEventListener("click", () => {
                    buttons.forEach((b) => b.classList.remove("active"));
                    btn.classList.add("active");
                    document.querySelectorAll(`${targetSelector} [data-tab-panel]`).forEach((panel) => {
                        panel.style.display = panel.dataset.tabPanel === btn.dataset.tab ? "" : "none";
                    });
                });
            });
        });
    });
})();

/* =====================================================================
   HELPERS UMUM
   ===================================================================== */
function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined || isNaN(value)) return "-";
    return Number(value).toLocaleString("id-ID", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function formatDateID(dateStr) {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
}

function chartColors() {
    const styles = getComputedStyle(document.documentElement);
    return {
        pink: styles.getPropertyValue("--pink-500").trim(),
        pinkLight: styles.getPropertyValue("--pink-100").trim(),
        sky: styles.getPropertyValue("--sky-500").trim(),
        skyLight: styles.getPropertyValue("--sky-100").trim(),
        green: styles.getPropertyValue("--green-500").trim(),
        greenLight: styles.getPropertyValue("--green-100").trim(),
        ink700: styles.getPropertyValue("--ink-700").trim(),
        ink500: styles.getPropertyValue("--ink-500").trim(),
        ink100: styles.getPropertyValue("--ink-100").trim(),
    };
}
