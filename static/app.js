/* ----------------------------------------------------
   Conferenza Client App - API & Frontend Interactions
   ---------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
    // Detect page elements
    const confGrid = document.getElementById('conferences-grid');
    const flaggedList = document.getElementById('flagged-list');

    if (confGrid) {
        initDirectoryPage();
    }

    if (flaggedList) {
        initAdminPage();
    }
});

// Device Fingerprint Generation (Persistent UUID)
function getOrCreateDeviceID() {
    let deviceId = localStorage.getItem('conferenza_device_id');
    if (!deviceId) {
        // Use cryptographically secure UUID generator if supported
        if (self.crypto && typeof self.crypto.randomUUID === 'function') {
            deviceId = self.crypto.randomUUID();
        } else {
            // High-entropy fallback generator
            deviceId = 'dev_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
        }
        localStorage.setItem('conferenza_device_id', deviceId);
    }
    return deviceId;
}

// Toast System helper
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconClass = 'fa-info-circle';
    if (type === 'success') iconClass = 'fa-circle-check';
    if (type === 'error') iconClass = 'fa-circle-exclamation';

    toast.innerHTML = `
        <i class="fa-solid ${iconClass}"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    // Fade out and remove
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 4000);
}

// ----------------------------------------------------
// Directory Page Functionality
// ----------------------------------------------------
function initDirectoryPage() {
    const searchInput = document.getElementById('search-input');
    const clearSearchBtn = document.getElementById('clear-search');
    const filterChips = document.querySelectorAll('.filter-chip');
    const loader = document.getElementById('loader');
    const emptyState = document.getElementById('empty-state');
    const confGrid = document.getElementById('conferences-grid');
    const countText = document.getElementById('listings-count-text');

    let currentDomain = 'All';
    let searchQuery = '';
    let debounceTimer;

    // Fetch and Render logic
    async function fetchConferences() {
        // Show loader
        loader.classList.remove('hidden');
        confGrid.classList.add('hidden');
        emptyState.classList.add('hidden');

        try {
            const url = `/api/conferences?domain=${currentDomain}&search=${encodeURIComponent(searchQuery)}`;
            // Send Device ID header to retrieve the user's active vote states
            const response = await fetch(url, {
                headers: {
                    'X-Device-ID': getOrCreateDeviceID()
                }
            });
            if (!response.ok) throw new Error("Failed to fetch conferences");
            
            const conferences = await response.json();
            renderConferences(conferences);
        } catch (error) {
            console.error(error);
            showToast("Failed to reload conference feed", "error");
            loader.classList.add('hidden');
        }
    }

    function renderConferences(conferences) {
        confGrid.innerHTML = '';
        loader.classList.add('hidden');

        if (conferences.length === 0) {
            emptyState.classList.remove('hidden');
            countText.textContent = 'Found 0 Conferences';
            return;
        }

        countText.textContent = `Found ${conferences.length} Conference${conferences.length === 1 ? '' : 's'}`;
        confGrid.classList.remove('hidden');

        conferences.forEach(conf => {
            const card = document.createElement('article');
            card.className = 'conference-card glass-panel';
            card.id = `conf-card-${conf.id}`;

            const domainClass = `domain-${conf.domain.toLowerCase()}`;
            const isVerified = conf.verified === 1;

            // Format dates
            let dateStr = conf.start_date;
            if (conf.end_date && conf.end_date !== conf.start_date) {
                dateStr += ` to ${conf.end_date}`;
            }

            // Trust calculation: ratio of positive votes
            const upvotes = conf.upvotes || 0;
            const downvotes = conf.downvotes || 0;
            const totalVotes = upvotes + downvotes;
            const trustPercentage = totalVotes > 0 ? Math.round((upvotes / totalVotes) * 100) : 100;

            const isUpvoteActive = conf.user_vote === 'up' ? 'active' : '';
            const isDownvoteActive = conf.user_vote === 'down' ? 'active' : '';

            card.innerHTML = `
                <div class="card-header-bar">
                    <span class="domain-badge ${domainClass}">${conf.domain}</span>
                    ${isVerified ? `
                        <span class="verified-tag">
                            <i class="fa-solid fa-shield-halved"></i> Verified
                        </span>
                    ` : ''}
                </div>
                <div class="card-body">
                    <h3 class="card-title">${escapeHTML(conf.title)}</h3>
                    <div class="card-meta">
                        <div class="meta-item">
                            <i class="fa-regular fa-calendar"></i>
                            <span>${dateStr}</span>
                        </div>
                        <div class="meta-item">
                            <i class="fa-solid fa-location-dot"></i>
                            <span>${escapeHTML(conf.location)}</span>
                        </div>
                    </div>
                    <p class="card-description">${escapeHTML(conf.description)}</p>
                </div>
                <div class="trust-gauge-box">
                    <div class="trust-meter-label">
                        <span>Community Vetted</span>
                        <span>${trustPercentage}% Trust</span>
                    </div>
                    <div class="trust-meter-bar">
                        <div class="trust-meter-fill" style="width: ${trustPercentage}%"></div>
                    </div>
                </div>
                <div class="card-action-bar">
                    <a href="${conf.url}" target="_blank" rel="noopener noreferrer" class="visit-btn">
                        <i class="fa-solid fa-up-right-from-square"></i> Visit Site
                    </a>
                    <div class="voting-container">
                        <button class="vote-btn vote-up ${isUpvoteActive}" data-id="${conf.id}" aria-label="Upvote conference">
                            <i class="fa-regular fa-thumbs-up"></i> <span class="vote-count">${upvotes}</span>
                        </button>
                        <button class="vote-btn vote-down ${isDownvoteActive}" data-id="${conf.id}" aria-label="Report suspicious conference">
                            <i class="fa-regular fa-thumbs-down"></i> <span class="vote-count">${downvotes}</span>
                        </button>
                    </div>
                </div>
            `;

            // Attach vote event listeners
            const upBtn = card.querySelector('.vote-up');
            const downBtn = card.querySelector('.vote-down');

            upBtn.addEventListener('click', () => sendVote(conf.id, 'up', card));
            downBtn.addEventListener('click', () => sendVote(conf.id, 'down', card));

            confGrid.appendChild(card);
        });
    }

    async function sendVote(confId, type, cardElement) {
        try {
            const response = await fetch(`/api/conferences/${confId}/vote`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Device-ID': getOrCreateDeviceID()
                },
                body: JSON.stringify({ type })
            });

            if (!response.ok) throw new Error("Failed to submit vote");
            const result = await response.json();

            if (result.success) {
                // Update specific card vote buttons and counters without full refetch
                const upBtn = cardElement.querySelector('.vote-up');
                const downBtn = cardElement.querySelector('.vote-down');
                
                upBtn.querySelector('.vote-count').textContent = result.upvotes;
                downBtn.querySelector('.vote-count').textContent = result.downvotes;

                // Adjust active toggle styling
                upBtn.classList.remove('active');
                downBtn.classList.remove('active');
                
                if (result.user_vote === 'up') {
                    upBtn.classList.add('active');
                } else if (result.user_vote === 'down') {
                    downBtn.classList.add('active');
                }

                // Update trust meter
                const total = result.upvotes + result.downvotes;
                const ratio = total > 0 ? Math.round((result.upvotes / total) * 100) : 100;
                
                cardElement.querySelector('.trust-meter-label span:last-child').textContent = `${ratio}% Trust`;
                cardElement.querySelector('.trust-meter-fill').style.width = `${ratio}%`;

                // Custom notifications based on database outcome
                if (result.action === 'added') {
                    showToast(type === 'up' ? "Voted: Authentic listing" : "Flagged as suspicious", type === 'up' ? "success" : "error");
                } else if (result.action === 'retracted') {
                    showToast("Your vote has been retracted", "info");
                } else if (result.action === 'toggled') {
                    showToast("Your vote has been updated", "success");
                }
            }
        } catch (error) {
            console.error(error);
            showToast("Failed to register vote", "error");
        }
    }

    // Debounced Search listener
    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim();
        
        // Show/hide clear button
        if (searchQuery) {
            clearSearchBtn.style.display = 'block';
        } else {
            clearSearchBtn.style.display = 'none';
        }

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchConferences();
        }, 300);
    });

    // Clear search button
    clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        searchQuery = '';
        clearSearchBtn.style.display = 'none';
        fetchConferences();
    });

    // Domain filters listener
    filterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            filterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentDomain = chip.dataset.domain;
            fetchConferences();
        });
    });

    // Initial fetch
    fetchConferences();
}

// ----------------------------------------------------
// Admin Page Functionality
// ----------------------------------------------------
function initAdminPage() {
    const flaggedList = document.getElementById('flagged-list');
    const loader = document.getElementById('admin-loader');
    const emptyState = document.getElementById('admin-empty-state');
    const badgeCount = document.getElementById('flagged-count-badge');
    const scrapeBtn = document.getElementById('trigger-scrape-btn');
    const modelStatus = document.getElementById('ai-mode-status');

    // Fetch and render flagged conferences
    async function fetchFlagged() {
        loader.classList.remove('hidden');
        flaggedList.classList.add('hidden');
        emptyState.classList.add('hidden');

        try {
            const response = await fetch('/api/admin/flagged');
            if (!response.ok) throw new Error("Failed to fetch flagged items");
            
            const data = await response.json();
            
            // Render model status if available
            if (data.gemini_active !== undefined) {
                if (data.gemini_active) {
                    modelStatus.innerHTML = `<i class="fa-solid fa-circle-dot mode-indicator-green"></i> Live Gemini AI Mode Active`;
                } else {
                    modelStatus.innerHTML = `<i class="fa-solid fa-circle-dot mode-indicator-orange"></i> Local Heuristic Mode (Simulating AI)`;
                }
            } else {
                modelStatus.innerHTML = `<i class="fa-solid fa-circle-dot mode-indicator-green"></i> Server Online`;
            }
            
            // Conferences array
            const conferences = data.conferences !== undefined ? data.conferences : data;
            renderFlaggedList(conferences);
        } catch (error) {
            console.error(error);
            showToast("Failed to fetch review queue", "error");
            loader.classList.add('hidden');
        }
    }

    function renderFlaggedList(conferences) {
        flaggedList.innerHTML = '';
        loader.classList.add('hidden');
        badgeCount.textContent = conferences.length;

        if (conferences.length === 0) {
            emptyState.classList.remove('hidden');
            return;
        }

        flaggedList.classList.remove('hidden');

        conferences.forEach(conf => {
            const card = document.createElement('article');
            card.className = 'flagged-card glass-panel';
            card.id = `flagged-card-${conf.id}`;

            let dateStr = conf.start_date;
            if (conf.end_date && conf.end_date !== conf.start_date) {
                dateStr += ` to ${conf.end_date}`;
            }

            card.innerHTML = `
                <div class="ai-alert-box">
                    <i class="fa-solid fa-triangle-exclamation ai-alert-icon"></i>
                    <div class="ai-alert-content">
                        <h4>AI Flag Reason</h4>
                        <p>${escapeHTML(conf.ai_reason)}</p>
                    </div>
                </div>
                <div class="flagged-details">
                    <div class="flagged-info">
                        <h3>${escapeHTML(conf.title)}</h3>
                        <div class="card-meta">
                            <div class="meta-item">
                                <span class="domain-badge domain-${conf.domain.toLowerCase()}">${conf.domain}</span>
                            </div>
                            <div class="meta-item">
                                <i class="fa-regular fa-calendar"></i>
                                <span>${dateStr}</span>
                            </div>
                            <div class="meta-item">
                                <i class="fa-solid fa-location-dot"></i>
                                <span>${escapeHTML(conf.location)}</span>
                            </div>
                            <div class="meta-item">
                                <i class="fa-solid fa-link"></i>
                                <a href="${conf.url}" target="_blank" rel="noopener noreferrer" style="color: var(--primary-light)">${escapeHTML(conf.url)}</a>
                            </div>
                            <div class="meta-item">
                                <i class="fa-solid fa-circle-info"></i>
                                <span>Source: ${escapeHTML(conf.source)}</span>
                            </div>
                        </div>
                        <p style="margin-top: 1rem; color: var(--text-secondary); font-size: 0.9rem;">${escapeHTML(conf.description)}</p>
                    </div>
                    <div class="flagged-actions-box">
                        <button class="admin-approve-btn" data-id="${conf.id}">
                            <i class="fa-solid fa-check"></i> Approve & Publish
                        </button>
                        <button class="admin-reject-btn" data-id="${conf.id}">
                            <i class="fa-solid fa-trash-can"></i> Reject & Delete
                        </button>
                    </div>
                </div>
            `;

            // Attach admin actions
            const approveBtn = card.querySelector('.admin-approve-btn');
            const rejectBtn = card.querySelector('.admin-reject-btn');

            approveBtn.addEventListener('click', () => handleApproval(conf.id, 'approve'));
            rejectBtn.addEventListener('click', () => handleApproval(conf.id, 'reject'));

            flaggedList.appendChild(card);
        });
    }

    async function handleApproval(confId, action) {
        const card = document.getElementById(`flagged-card-${confId}`);
        try {
            const url = `/api/admin/${action}/${confId}`;
            const response = await fetch(url, { method: 'POST' });
            
            if (!response.ok) throw new Error(`Failed to ${action} conference`);
            const result = await response.json();

            if (result.success) {
                // Animate removal
                card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
                card.style.opacity = '0';
                card.style.transform = 'translateX(50px)';
                
                setTimeout(() => {
                    card.remove();
                    // Update count
                    const currentCount = parseInt(badgeCount.textContent) - 1;
                    badgeCount.textContent = currentCount;
                    
                    if (currentCount === 0) {
                        emptyState.classList.remove('hidden');
                        flaggedList.classList.add('hidden');
                    }
                }, 350);

                if (action === 'approve') {
                    showToast("Conference approved and verified!", "success");
                } else {
                    showToast("Conference deleted from review logs", "info");
                }
            }
        } catch (error) {
            console.error(error);
            showToast(`Error performing admin action`, "error");
        }
    }

    // Trigger Scraper Action
    scrapeBtn.addEventListener('click', async () => {
        scrapeBtn.disabled = true;
        scrapeBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Crawling and Vetting Web...`;
        showToast("Scraper starting. Fetching & analyzing listings...", "info");

        try {
            const response = await fetch('/api/admin/trigger-scrape', { method: 'POST' });
            if (!response.ok) throw new Error("Scraping failed");
            
            const result = await response.json();
            if (result.success) {
                showToast(`Scrape completed! Added ${result.new_count} new, flagged ${result.flagged_count} suspect events.`, "success");
                // Reload flagged list
                fetchFlagged();
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            console.error(error);
            showToast("Scraper encountered an error during indexing", "error");
        } finally {
            scrapeBtn.disabled = false;
            scrapeBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-down"></i> Trigger Scrape Now`;
        }
    });

    // Initial fetch
    fetchFlagged();
}

// Helpers
function escapeHTML(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
