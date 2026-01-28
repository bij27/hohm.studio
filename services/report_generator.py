from typing import List, Dict
import json
from models.schemas import PostureIssueType

class ReportGenerator:
    """
    Generates summary statistics and recommendations based on session logs.
    """
    @staticmethod
    def identify_common_issues(logs: List[Dict]) -> List[PostureIssueType]:
        issue_counts = {}
        for log in logs:
            issues = json.loads(log['issues'])
            for issue in issues:
                issue_type = issue['type']
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        # Sort by frequency
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [PostureIssueType(x[0]) for x in sorted_issues]

    @staticmethod
    def get_recommendations(common_issues: List[PostureIssueType]) -> List[str]:
        recommendations = []
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
        
        if not recommendations:
            recommendations.append("Great job! Keep up the good posture.")
            
        return recommendations[:3] # Return top 3
