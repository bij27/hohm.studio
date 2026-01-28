const statDuration = document.getElementById('stat-duration');
const statGood = document.getElementById('stat-good');
const statScore = document.getElementById('stat-score');
const statLogs = document.getElementById('stat-logs');
const sessionGrade = document.getElementById('session-grade');
const timeline = document.getElementById('session-timeline');
const commonIssuesEl = document.getElementById('common-issues');
const recommendationsEl = document.getElementById('recommendations');

let sessionData = null;

// Security: HTML escape function to prevent XSS
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

async function loadSessionData() {
    try {
        const response = await fetch(`/api/sessions/${SESSION_ID}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        sessionData = await response.json();
        renderSession(sessionData);
    } catch (err) {
        console.error("Error loading session:", err);
        document.getElementById('session-title').textContent = 'Session Not Found';
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
        timeline.innerHTML = ''; // Clear existing
        logs.forEach((log) => {
            const segment = document.createElement('div');
            segment.className = 'timeline-segment';
            segment.style.flex = 1;
            segment.style.backgroundColor = log.status === 'good' ? 'var(--color-good)' :
                                           log.status === 'warning' ? 'var(--color-accent)' : 'var(--color-bad)';
            segment.title = `${new Date(log.timestamp).toLocaleTimeString()} - Score: ${log.score}`;
            timeline.appendChild(segment);
        });
    } else {
        timeline.innerHTML = '<div style="flex: 1; background: var(--color-text-secondary); opacity: 0.3;"></div>';
    }

    // Common Issues - styled as tags (escape content to prevent XSS)
    if (common_issues && common_issues.length > 0) {
        commonIssuesEl.innerHTML = common_issues.map(issue => `
            <span class="issue-tag">${escapeHtml(String(issue).replace(/_/g, ' '))}</span>
        `).join('');
    } else {
        commonIssuesEl.innerHTML = '<div class="empty-state">No persistent issues detected. Great work!</div>';
    }

    // Recommendations (escape content to prevent XSS)
    if (recommendations && recommendations.length > 0) {
        recommendationsEl.innerHTML = recommendations.map(rec => `<li>${escapeHtml(rec)}</li>`).join('');
    } else {
        recommendationsEl.innerHTML = '<li>Keep up the good work! Your posture was excellent.</li>';
    }
}

loadSessionData();
