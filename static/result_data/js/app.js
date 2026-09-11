document.addEventListener("DOMContentLoaded", () => {
    const revealItems = document.querySelectorAll("[data-reveal]");
    if (!("IntersectionObserver" in window)) return;
    document.body.classList.add("app-ready");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        revealItems.forEach((item) => item.classList.add("is-visible"));
        return;
    }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08 });
    revealItems.forEach((item) => observer.observe(item));
});
