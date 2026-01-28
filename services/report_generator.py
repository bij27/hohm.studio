from typing import List, Dict, Optional
import json
from models.schemas import PostureIssueType


class ReportGenerator:
    """
    Generates summary statistics and recommendations based on session logs.
    """

    # Thresholds for session-level warnings
    GOOD_POSTURE_THRESHOLD = 60  # Below this % triggers recommendations
    AVERAGE_SCORE_THRESHOLD = 7.0  # Below this triggers recommendations

    @staticmethod
    def identify_common_issues(logs: List[Dict]) -> List[PostureIssueType]:
        issue_counts = {}
        for log in logs:
            try:
                # Handle both string (JSON) and already-parsed list
                issues = log.get('issues', [])
                if isinstance(issues, str):
                    try:
                        issues = json.loads(issues)
                    except json.JSONDecodeError:
                        issues = []

                if not isinstance(issues, list):
                    continue

                for issue in issues:
                    if not isinstance(issue, dict):
                        continue
                    issue_type = issue.get('type', '')
                    if issue_type:
                        issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
            except Exception:
                # Skip malformed logs
                continue

        # Sort by frequency
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)

        # Safely convert to PostureIssueType
        result = []
        for issue_type, _ in sorted_issues:
            try:
                result.append(PostureIssueType(issue_type))
            except ValueError:
                # Invalid issue type, skip
                continue
        return result

    @staticmethod
    def get_recommendations(
        common_issues: List[PostureIssueType],
        good_posture_percentage: Optional[float] = None,
        average_score: Optional[float] = None
    ) -> List[str]:
        recommendations = []

        # Add issue-specific recommendations
        for issue in common_issues:
            if issue == PostureIssueType.FORWARD_HEAD:
                recommendations.append("Position your monitor at eye level to prevent looking down.")
            elif issue == PostureIssueType.SLOUCHING:
                recommendations.append("Use a chair with lumbar support or a lumbar roll.")
            elif issue == PostureIssueType.UNEVEN_SHOULDERS:
                recommendations.append("Check if your desk or chair height is uneven, and avoid leaning on one side.")
            elif issue == PostureIssueType.NECK_TILT:
                recommendations.append("Avoid cradling a phone between your shoulder and ear.")
            elif issue == PostureIssueType.SCREEN_DISTANCE:
                recommendations.append("Increase font size or move your monitor closer so you don't lean in to read.")

        # If no specific issues but session stats are poor, add general recommendations
        if not recommendations:
            needs_improvement = False

            if good_posture_percentage is not None and good_posture_percentage < ReportGenerator.GOOD_POSTURE_THRESHOLD:
                needs_improvement = True
            if average_score is not None and average_score < ReportGenerator.AVERAGE_SCORE_THRESHOLD:
                needs_improvement = True

            if needs_improvement:
                # Add general posture improvement recommendations
                recommendations.append("Take regular breaks to stand and stretch every 30 minutes.")
                recommendations.append("Focus on maintaining a neutral spine position while seated.")
                if good_posture_percentage is not None and good_posture_percentage < 50:
                    recommendations.append("Consider using a posture reminder app or setting hourly check-in alarms.")
                else:
                    recommendations.append("Practice chin tucks and shoulder blade squeezes to strengthen postural muscles.")
            else:
                recommendations.append("Great job! Keep up the good posture.")

        return recommendations[:3]  # Return top 3
