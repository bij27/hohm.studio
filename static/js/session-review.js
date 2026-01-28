const statDuration = document.getElementById('stat-duration');
const statGood = document.getElementById('stat-good');
const statScore = document.getElementById('stat-score');
const statLogs = document.getElementById('stat-logs');
const sessionGrade = document.getElementById('session-grade');
const timeline = document.getElementById('session-timeline');
const gallery = document.getElementById('screenshot-gallery');
const commonIssuesEl = document.getElementById('common-issues');
const recommendationsEl = document.getElementById('recommendations');
const modal = document.getElementById('modal');
const modalImg = document.getElementById('modal-img');
const modalClose = document.getElementById('modal-close');

let sessionData = null;

// Security: HTML escape function to prevent XSS
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Security: Validate and sanitize filename
function sanitizeFilename(filename) {
    if (!filename || typeof filename !== 'string') return '';
    // Only allow alphanumeric, dash, underscore, and dot
    return filename.replace(/[^a-zA-Z0-9._-]/g, '');
}

async function loadSessionData() {
    try {
        const response = await fetch(`/api/sessions/${SESSION_ID}`);
        sessionData = await response.json();
        renderSession(sessionData);
    } catch (err) {
        console.error("Error loading session:", err);
    }
}

function getGradeColor(score) {
    if (score >= 8) return 'var(--color-good)';
    if (score >= 6) return 'var(--color-accent)';
    return 'var(--color-bad)';
}

function getGradeLabel(score) {
    if (score >= 9) return 'Excellent';
    if (score >= 8) return 'Great';
    if (score >= 7) return 'Good';
    if (score >= 6) return 'Fair';
    if (score >= 5) return 'Needs Work';
    return 'Poor';
}

function renderSession(data) {
    const { session, logs, common_issues, recommendations } = data;

    // Grade display
    const grade = session.average_score.toFixed(1);
    if (sessionGrade) {
        sessionGrade.innerHTML = `
            <div style="font-size: 3rem; font-weight: 300; color: ${getGradeColor(session.average_score)};">${grade}</div>
            <div style="font-size: 0.75rem; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 1px;">${getGradeLabel(session.average_score)}</div>
        `;
    }

    // Stats
    statDuration.innerText = `${Math.round(session.duration_minutes)}m`;
    statGood.innerText = `${Math.round(session.good_posture_percentage)}%`;
    statScore.innerText = grade;
    statLogs.innerText = session.total_logs;

    document.getElementById('session-date').innerText = new Date(session.start_time).toLocaleString();

    // Timeline
    if (logs.length > 0) {
        logs.forEach((log, index) => {
            const segment = document.createElement('div');
            segment.className = 'timeline-segment';
            segment.style.flex = 1;
            segment.style.backgroundColor = log.status === 'good' ? 'var(--color-good)' :
                                           log.status === 'warning' ? 'var(--color-accent)' : 'var(--color-bad)';
            segment.title = `${new Date(log.timestamp).toLocaleTimeString()} - Score: ${log.score}`;
            segment.onclick = () => scrollToLog(index);
            timeline.appendChild(segment);
        });
    }

    // Gallery - show bad posture screenshots (score < 7)
    const badLogs = logs.filter(log => log.screenshot_path && log.score < 7);

    if (badLogs.length === 0) {
        gallery.innerHTML = '<p style="color: var(--color-text-secondary); text-align: center; padding: 40px;">No posture issues captured. Great job!</p>';
    } else {
        badLogs.forEach((log, index) => {
            const card = document.createElement('div');
            card.className = 'screenshot-card';
            card.id = `log-${index}`;

            const rawFilename = log.screenshot_path.split('\\').pop().split('/').pop();
            const filename = sanitizeFilename(rawFilename);
            if (!filename) return; // Skip invalid filenames
            const imgUrl = `/static/data/screenshots/${filename}`;

            // Parse issues for tips
            let issues = [];
            try {
                issues = JSON.parse(log.issues || '[]');
            } catch (e) {}

            // Escape user-generated content to prevent XSS
            const tipText = escapeHtml(issues.length > 0 ? (issues[0].advice || 'Adjust your posture') : 'Check your posture');
            const scoreValue = parseFloat(log.score) || 0;

            card.innerHTML = `
                <img src="${imgUrl}" alt="Posture issue">
                <div class="screenshot-info">
                    <strong>${escapeHtml(new Date(log.timestamp).toLocaleTimeString())}</strong>
                    <div style="color: var(--color-bad); margin: 4px 0;">Score: ${scoreValue.toFixed(1)}/10</div>
                    <div style="font-size: 0.75rem; color: var(--color-accent);">${tipText}</div>
                </div>
            `;

            card.onclick = () => openModal(imgUrl, log);
            gallery.appendChild(card);
        });
    }

    // Common Issues - styled as tags (escape content to prevent XSS)
    if (common_issues.length > 0) {
        commonIssuesEl.innerHTML = common_issues.map(issue => `
            <span class="issue-tag">${escapeHtml(String(issue).replace(/_/g, ' '))}</span>
        `).join('');
    } else {
        commonIssuesEl.innerHTML = '<p style="color: var(--color-text-secondary);">No persistent issues detected.</p>';
    }

    // Recommendations (escape content to prevent XSS)
    if (recommendations.length > 0) {
        recommendationsEl.innerHTML = recommendations.map(rec => `<li>${escapeHtml(rec)}</li>`).join('');
    } else {
        recommendationsEl.innerHTML = '<li>Keep up the good work! Your posture was excellent.</li>';
    }
}

function scrollToLog(index) {
    const el = document.getElementById(`log-${index}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function openModal(imgUrl, log) {
    modalImg.src = imgUrl;

    let issues = [];
    try {
        issues = JSON.parse(log.issues || '[]');
    } catch (e) {}

    // Using innerText is safe (auto-escapes) but also validate the data
    const issueText = issues.map(i => String(i.advice || i.type || '')).join(' | ') || 'Posture issue detected';
    const scoreValue = parseFloat(log.score) || 0;
    document.getElementById('modal-caption').innerText = `${new Date(log.timestamp).toLocaleTimeString()} - Score: ${scoreValue.toFixed(1)}/10 - ${issueText}`;
    modal.style.display = 'flex';
}

modalClose.onclick = () => modal.style.display = 'none';
window.onclick = (event) => {
    if (event.target == modal) modal.style.display = 'none';
};

// PDF Download function
async function downloadPDF() {
    if (!sessionData) {
        alert('Session data not loaded yet');
        return;
    }

    const { session, logs, common_issues, recommendations } = sessionData;

    // Create printable HTML
    const printContent = `
        <!DOCTYPE html>
        <html>
        <head>
            <title>hohm.studio Session Report</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 40px; color: #333; max-width: 800px; margin: 0 auto; }
                h1 { color: #7c9a92; font-weight: 300; border-bottom: 2px solid #7c9a92; padding-bottom: 10px; }
                h2 { color: #666; font-weight: 400; margin-top: 30px; }
                .grade { font-size: 4rem; color: #7c9a92; text-align: center; margin: 20px 0; }
                .grade-label { text-align: center; color: #666; font-size: 1.2rem; }
                .stats { display: flex; justify-content: space-around; margin: 30px 0; padding: 20px; background: #f5f5f5; border-radius: 8px; }
                .stat { text-align: center; }
                .stat-value { font-size: 1.5rem; font-weight: 600; }
                .stat-label { font-size: 0.8rem; color: #888; }
                .issue { display: inline-block; background: #fff3e0; color: #d4a574; padding: 4px 12px; border-radius: 15px; margin: 4px; font-size: 0.9rem; }
                .rec { padding: 10px; background: #e8f5e9; border-left: 3px solid #7c9a92; margin: 8px 0; }
                .footer { margin-top: 40px; text-align: center; color: #888; font-size: 0.8rem; }
            </style>
        </head>
        <body>
            <h1>hohm.studio Session Report</h1>
            <p>${new Date(session.start_time).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</p>

            <div class="grade">${session.average_score.toFixed(1)}/10</div>
            <div class="grade-label">${getGradeLabel(session.average_score)}</div>

            <div class="stats">
                <div class="stat">
                    <div class="stat-value">${Math.round(session.duration_minutes)}m</div>
                    <div class="stat-label">Duration</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${Math.round(session.good_posture_percentage)}%</div>
                    <div class="stat-label">Good Posture</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${session.total_logs}</div>
                    <div class="stat-label">Data Points</div>
                </div>
            </div>

            <h2>Areas for Improvement</h2>
            <div>
                ${common_issues.length > 0
                    ? common_issues.map(i => `<span class="issue">${escapeHtml(String(i).replace(/_/g, ' '))}</span>`).join('')
                    : '<p>No persistent issues detected. Great work!</p>'}
            </div>

            <h2>Recommendations</h2>
            ${recommendations.length > 0
                ? recommendations.map(r => `<div class="rec">${escapeHtml(r)}</div>`).join('')
                : '<div class="rec">Keep up the excellent posture habits!</div>'}

            <div class="footer">
                Generated by hohm.studio - Your posture determines your attitude.
            </div>
        </body>
        </html>
    `;

    // Open print dialog (user can save as PDF)
    const printWindow = window.open('', '_blank');
    printWindow.document.write(printContent);
    printWindow.document.close();
    printWindow.print();
}

loadSessionData();
