// Load structured data (JSON-LD) from external file
document.addEventListener('DOMContentLoaded', function() {
    fetch('/structured-data.jsonld')
        .then(response => response.json())
        .then(data => {
            const script = document.createElement('script');
            script.type = 'application/ld+json';
            script.textContent = JSON.stringify(data);
            document.head.appendChild(script);
        })
        .catch(error => {
            console.error('Failed to load structured data:', error);
        });
});
