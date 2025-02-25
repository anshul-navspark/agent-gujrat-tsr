document.addEventListener('DOMContentLoaded', function() {
    const anyrorForm = document.getElementById('anyror-form');
    const tsrForm = document.getElementById('tsr-form');
    const anyrorStatus = document.getElementById('anyror-status');
    const tsrStatus = document.getElementById('tsr-status');
    const downloadsArea = document.getElementById('downloads-area');
    
    // Handle AnyRoR form submission
    anyrorForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Show loading message
        anyrorStatus.innerHTML = `
            <div class="status-message status-loading">
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Fetching land record data... This may take a minute.
            </div>
        `;
        
        const formData = new FormData(anyrorForm);
        
        fetch('/fetch-anyror', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                anyrorStatus.innerHTML = `
                    <div class="status-message status-success">
                        <strong>Success!</strong> ${data.message}
                    </div>
                `;
                
                // Add download link for PDF
                addDownloadLink(data.pdf_path, "Download Land Record PDF");
            } else {
                anyrorStatus.innerHTML = `
                    <div class="status-message status-error">
                        <strong>Error!</strong> ${data.message}
                    </div>
                `;
            }
        })
        .catch(error => {
            anyrorStatus.innerHTML = `
                <div class="status-message status-error">
                    <strong>Error!</strong> An unexpected error occurred.
                </div>
            `;
            console.error('Error:', error);
        });
    });
    
    // Handle TSR form submission
    tsrForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Show loading message
        tsrStatus.innerHTML = `
            <div class="status-message status-loading">
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Generating TSR document... This may take a minute.
            </div>
        `;
        
        const formData = new FormData(tsrForm);
        
        // Log the form data to console for debugging
        console.log("File being uploaded:", formData.get('pdf_file'));
        
        fetch('/generate-tsr', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tsrStatus.innerHTML = `
                    <div class="status-message status-success">
                        <strong>Success!</strong> ${data.message}
                    </div>
                `;
                
                // Add download link for TSR
                addDownloadLink(data.tsr_path, "Download TSR Document");
            } else {
                tsrStatus.innerHTML = `
                    <div class="status-message status-error">
                        <strong>Error!</strong> ${data.message}
                    </div>
                `;
            }
        })
        .catch(error => {
            tsrStatus.innerHTML = `
                <div class="status-message status-error">
                    <strong>Error!</strong> An unexpected error occurred.
                </div>
            `;
            console.error('Error:', error);
        });
    });
    
    // Function to add download links
    function addDownloadLink(filePath, text) {
        const noFilesMessage = downloadsArea.querySelector('p');
        if (noFilesMessage) {
            downloadsArea.innerHTML = '';
        }
        
        const link = document.createElement('a');
        link.href = `/download/${filePath}`;
        link.className = 'download-link';
        link.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-download me-2" viewBox="0 0 16 16">
                <path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/>
                <path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/>
            </svg>
            ${text}
        `;
        downloadsArea.appendChild(link);
    }
}); 