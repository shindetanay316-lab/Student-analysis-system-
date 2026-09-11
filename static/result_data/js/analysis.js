document.addEventListener("DOMContentLoaded", () => {
    const source = document.getElementById("analysis-data");
    if (!source || typeof Chart === "undefined") return;

    const analysis = JSON.parse(source.textContent);
    const styles = getComputedStyle(document.documentElement);
    const color = (name) => styles.getPropertyValue(name).trim();
    const palette = {
        navy: color("--brand-navy"),
        blue: color("--brand-blue"),
        cyan: color("--brand-cyan"),
        green: color("--status-success"),
        amber: color("--status-warning"),
        red: color("--status-danger"),
        slate: color("--text-muted"),
        grid: color("--chart-grid"),
    };
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    Chart.defaults.color = palette.slate;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.animation.duration = reduceMotion ? 0 : 250;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;

    const commonScales = {
        x: { grid: { display: false }, border: { display: false } },
        y: { beginAtZero: true, grid: { color: palette.grid }, border: { display: false }, ticks: { precision: 0 } },
    };
    const tooltip = {
        backgroundColor: palette.navy,
        titleColor: "#ffffff",
        bodyColor: "#ffffff",
        padding: 12,
        cornerRadius: 8,
        displayColors: true,
    };

    const createChart = (id, config) => {
        const canvas = document.getElementById(id);
        if (canvas) new Chart(canvas, config);
    };

    createChart("sgpaChart", {
        type: "bar",
        data: {
            labels: analysis.sgpa_distribution.map((item) => item.label),
            datasets: [{ label: "Students", data: analysis.sgpa_distribution.map((item) => item.count), backgroundColor: palette.blue, borderRadius: 2, maxBarThickness: 52 }],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: commonScales, plugins: { legend: { display: false }, tooltip } },
    });

    const statusColor = (label) => ({ Pass: palette.green, Fail: palette.red, Cancel: palette.slate }[label] || palette.amber);
    createChart("resultStatusChart", {
        type: "doughnut",
        data: {
            labels: analysis.result_status.map((item) => item.label),
            datasets: [{ data: analysis.result_status.map((item) => item.count), backgroundColor: analysis.result_status.map((item) => statusColor(item.label)), borderWidth: 0, spacing: 3 }],
        },
        options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom" }, tooltip } },
    });

    createChart("subjectChart", {
        type: "bar",
        data: {
            labels: analysis.subject_performance.map((item) => item.code),
            datasets: [
                { label: "Average marks %", data: analysis.subject_performance.map((item) => item.average_percentage), backgroundColor: palette.blue, borderRadius: 2 },
                { label: "Pass rate %", data: analysis.subject_performance.map((item) => item.pass_rate), backgroundColor: palette.cyan, borderRadius: 2 },
            ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { ...commonScales, y: { ...commonScales.y, suggestedMax: 100, max: 100 } }, plugins: { legend: { position: "bottom" }, tooltip } },
    });

    const validationColor = (label) => ({ Valid: palette.green, Warning: palette.amber, Error: palette.red, Skipped: palette.slate }[label] || palette.blue);
    createChart("validationChart", {
        type: "doughnut",
        data: {
            labels: analysis.validation_status.map((item) => item.label),
            datasets: [{ data: analysis.validation_status.map((item) => item.count), backgroundColor: analysis.validation_status.map((item) => validationColor(item.label)), borderWidth: 0, spacing: 3 }],
        },
        options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom" }, tooltip } },
    });

    createChart("gradeChart", {
        type: "bar",
        data: {
            labels: analysis.grade_distribution.map((item) => item.grade),
            datasets: [{ label: "Subject results", data: analysis.grade_distribution.map((item) => item.count), backgroundColor: palette.navy, borderRadius: 2, maxBarThickness: 40 }],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: commonScales, plugins: { legend: { display: false }, tooltip } },
    });

    createChart("componentChart", {
        type: "bar",
        data: {
            labels: analysis.component_performance.map((item) => item.component),
            datasets: [{ label: "Average attainment %", data: analysis.component_performance.map((item) => item.average_percentage), backgroundColor: palette.cyan, borderRadius: 2, maxBarThickness: 45 }],
        },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, scales: { x: { ...commonScales.y, max: 100 }, y: { ...commonScales.x } }, plugins: { legend: { display: false }, tooltip } },
    });
});
