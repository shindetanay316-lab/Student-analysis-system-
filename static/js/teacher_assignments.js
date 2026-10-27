/* Search the server-loaded semester subjects without disabling native options. */
(() => {
    const select = document.getElementById('subject');
    if (!select) return;
    const search = document.getElementById('subject-search');
    const status = document.getElementById('subject-search-status');
    const options = Array.from(select.options).filter(option => option.value)
        .map(option => ({ value: option.value, text: option.textContent }));
    const groups = JSON.parse(document.getElementById('assignment-roster-data').textContent);
    const table = document.getElementById('roster-table');
    const rosterStatus = document.getElementById('roster-status');

    function preview() {
        const body = table.querySelector('tbody');
        body.replaceChildren();
        const rows = groups[select.value] || [];
        table.hidden = !rows.length;
        rosterStatus.textContent = !select.value ? 'Select a subject to see its enrolled cohorts, divisions and practical batches.'
            : !rows.length ? 'No students are enrolled for this subject in the loaded year and semester. You can assign the teacher now; configure the student roster before uploading marks or attendance.'
            : `${rows.reduce((total, row) => total + row.count, 0)} enrolled students across ${rows.length} groups.`;
        for (const group of rows) {
            const row = document.createElement('tr');
            for (const value of [group.cohort, group.division, group.batch, group.count]) {
                const cell = document.createElement('td');
                cell.textContent = String(value);
                row.appendChild(cell);
            }
            body.appendChild(row);
        }
    }

    search.addEventListener('input', () => {
        const previous = select.value;
        const query = search.value.trim().toLocaleLowerCase();
        const matches = options.filter(option => option.text.toLocaleLowerCase().includes(query));
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = matches.length ? 'Select a subject below' : 'No subjects match this search';
        select.replaceChildren(placeholder);
        for (const item of matches) {
            const option = document.createElement('option');
            option.value = item.value;
            option.textContent = item.text;
            select.appendChild(option);
        }
        select.value = matches.some(option => option.value === previous) ? previous : '';
        status.textContent = `${matches.length} matching subjects. Click a subject to select it.`;
        preview();
    });
    select.addEventListener('change', preview);
    const year = document.getElementById('academic-year');
    const semester = document.getElementById('semester');
    const loadedYear = year.value;
    const loadedSemester = semester.value;
    function checkContext() {
        const changed = year.value.trim() !== loadedYear || semester.value !== loadedSemester;
        document.getElementById('assign-button').disabled = changed;
        document.getElementById('context-change-message').hidden = !changed;
    }
    year.addEventListener('input', checkContext);
    semester.addEventListener('change', checkContext);
    preview();
})();
