async function loadNetworkInfo() {
    try {
        const response = await fetch('/rpc/network-info');
        const data = await response.json();

        // Update Join the Network section
        document.getElementById('node-id').textContent = data.p2p_node_id;
        document.getElementById('chain-id').textContent = data.chain_id;

        // Update meta section
        document.getElementById('meta-node-id').textContent = data.p2p_node_id;
        document.getElementById('meta-chain-id').textContent = data.chain_id;

        // Update contact email
        if (data.contact_email) {
            document.getElementById('contact-email').textContent = data.contact_email;
            document.getElementById('contact-email-link').href = 'mailto:' + data.contact_email;
        }
    } catch (error) {
        console.error('Failed to load network info:', error);
        document.getElementById('node-id').textContent = 'unknown';
        document.getElementById('chain-id').textContent = 'unknown';
        document.getElementById('meta-node-id').textContent = 'unknown';
        document.getElementById('meta-chain-id').textContent = 'unknown';
        document.getElementById('contact-email').textContent = 'unknown';
    }
}

// Load network info on page load
document.addEventListener('DOMContentLoaded', loadNetworkInfo);
