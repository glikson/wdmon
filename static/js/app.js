let activeFilter = localStorage.getItem('activeFilter') || 'all';
let currentSort = JSON.parse(localStorage.getItem('currentSort')) || { column: null, ascending: true };

// Auto-refresh the page every 5 seconds
setInterval(() => {
    const oldBody = document.querySelector('tbody').innerHTML;
    const detailsVisible = document.getElementById('details-section').classList.contains('visible');
    const detailsTitle = document.querySelector('.details-title').textContent;
    const savedSort = { ...currentSort }; // Save current sort state
    
    fetch(window.location.pathname)
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            document.querySelector('tbody').innerHTML = doc.querySelector('tbody').innerHTML;
            
            // Restore sort state and apply sort
            currentSort = savedSort;
            if (currentSort.column !== null) {
                sortTable(currentSort.column, false); // Add false parameter to prevent direction toggle
            }
            filterRows(activeFilter);
            
            // Restore details if they were visible
            if (detailsVisible) {
                const deploymentName = detailsTitle.replace('Disruption Details: ', '');
                showDetails(deploymentName);
            }
        });
}, 5000);

function applyFilters() {
    const rows = document.querySelectorAll('tbody tr');
    const namespaceFilter = document.getElementById('namespaceFilter').value.toLowerCase();
    const typeFilter = document.getElementById('typeFilter').value;
    const workloadFilter = document.getElementById('workloadFilter').value.toLowerCase();
    const statusFilter = activeFilter;

    rows.forEach(row => {
        const namespace = row.cells[0].textContent.toLowerCase();
        const type = row.cells[1].textContent;
        const workload = row.cells[2].textContent.toLowerCase();
        const oomCount = parseInt(row.querySelector('.count-oom').textContent);
        const termCount = parseInt(row.querySelector('.count-term').textContent);
        const total = oomCount + termCount;

        const matchesNamespace = !namespaceFilter || namespace.includes(namespaceFilter);
        const matchesType = !typeFilter || type === typeFilter;
        const matchesWorkload = !workloadFilter || workload.includes(workloadFilter);
        const matchesStatus = statusFilter === 'all' ||
            (statusFilter === 'disrupted' && total > 0) ||
            (statusFilter === 'oom' && oomCount > 0) ||
            (statusFilter === 'termination' && termCount > 0);

        row.style.display = (matchesNamespace && matchesType && matchesWorkload && matchesStatus) ? '' : 'none';
    });
}

function filterRows(filter) {
    activeFilter = filter;
    localStorage.setItem('activeFilter', filter);
    const buttons = document.querySelectorAll('.filter-button');
    buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.filter === filter));
    applyFilters();
}

function sortTable(columnIndex, toggleDirection = true) {
    const table = document.querySelector('table');
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const headers = table.querySelectorAll('th');
    
    // Toggle sort direction if clicking the same column and toggleDirection is true
    if (currentSort.column === columnIndex && toggleDirection) {
        currentSort.ascending = !currentSort.ascending;
    } else if (currentSort.column !== columnIndex) {
        currentSort = { column: columnIndex, ascending: true };
    }
    
    // Update sort indicators
    headers.forEach(header => {
        header.classList.remove('sorted-asc', 'sorted-desc');
    });
    headers[columnIndex].classList.add(
        currentSort.ascending ? 'sorted-asc' : 'sorted-desc'
    );

    // Store sort state
    localStorage.setItem('currentSort', JSON.stringify(currentSort));

    rows.sort((a, b) => {
        const aValue = a.cells[columnIndex].textContent;
        const bValue = b.cells[columnIndex].textContent;
        
        if (aValue === '-' && bValue === '-') return 0;
        if (aValue === '-') return 1;
        if (bValue === '-') return -1;

        // Handle date sorting for Last Disruption column
        if (columnIndex === 2) {
            const aDate = new Date(aValue);
            const bDate = new Date(bValue);
            return currentSort.ascending ? aDate - bDate : bDate - aDate;
        }

        return currentSort.ascending ? 
            aValue.localeCompare(bValue) : 
            bValue.localeCompare(aValue);
    });

    const tbody = table.querySelector('tbody');
    rows.forEach(row => tbody.appendChild(row));
}

// Apply stored filter and sort on page load
document.addEventListener('DOMContentLoaded', () => {
    if (activeFilter !== 'all') {
        filterRows(activeFilter);
    }
    if (currentSort.column !== null) {
        sortTable(currentSort.column);
    }
});

function showDetails(workloadKey) {
    const detailsSection = document.getElementById('details-section');
    fetch(`/workload/${encodeURIComponent(workloadKey)}`)
        .then(response => response.json())
        .then(data => {
            // Update title and process namespace/type/name
            const [namespace, type, name] = workloadKey.split('/');
            detailsSection.querySelector('.details-title').textContent = 
                `Disruption Details: ${namespace}/${name} (${type})`;
            
            const tbody = detailsSection.querySelector('tbody');
            tbody.innerHTML = '';
            
            // Add rows with fade-in animation
            data.disruptions.forEach((disruption, index) => {
                const row = document.createElement('tr');
                row.style.animation = `fadeIn 0.3s ease-out ${index * 0.05}s both`;
                row.innerHTML = `
                    <td>${disruption.timestamp}</td>
                    <td>${disruption.pod}</td>
                    <td>${disruption.container}</td>
                    <td>
                        <span class="status-badge ${disruption.reason === 'OOMKilled' ? 'status-warning' : 'status-ok'}">
                            ${disruption.reason}
                        </span>
                    </td>
                `;
                tbody.appendChild(row);
            });
            
            detailsSection.classList.add('visible');
        });
}

function hideDetails() {
    const detailsSection = document.getElementById('details-section');
    detailsSection.classList.remove('visible');
}

function hideDrawer() {
    document.getElementById('details-drawer').classList.remove('open');
}

function showConfig() {
    fetch('/settings')
        .then(response => response.json())
        .then(data => {
            document.getElementById('retention').value = data.retention_hours;
            document.getElementById('config-modal').classList.add('visible');
        });
}

function hideConfig() {
    document.getElementById('config-modal').classList.remove('visible');
}

function saveConfig() {
    const retention = parseInt(document.getElementById('retention').value);
    fetch('/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({retention_hours: retention})
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            hideConfig();
        }
    });
}

function showSettings() {
    fetch('/settings')
        .then(response => response.json())
        .then(data => {
            document.getElementById('retention').value = data.retention_hours;
            document.getElementById('settings-modal').classList.add('visible');
        });
}

function hideSettings() {
    document.getElementById('settings-modal').classList.remove('visible');
}

function saveSettings() {
    const retention = parseInt(document.getElementById('retention').value);
    fetch('/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({retention_hours: retention})
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            hideSettings();
        }
    });
}
