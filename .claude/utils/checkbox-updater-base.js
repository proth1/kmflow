/**
 * Base Checkbox Updater
 *
 * Shared functionality for both ADO and JIRA checkbox updates
 * Based on the legacy acceptance_criteria_verification_agent.py
 */

class CheckboxUpdaterBase {
    constructor() {
        this.name = "CheckboxUpdaterBase";
    }

    /**
     * Extract keywords from criterion text
     * @param {string} text - Text to extract from
     * @returns {Array} Keywords
     */
    extractKeywords(text) {
        const stopWords = new Set([
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were',
            'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did'
        ]);

        const words = text.match(/\w+/g) || [];
        return words
            .filter(w => w.length > 3 && !stopWords.has(w.toLowerCase()))
            .slice(0, 5); // Top 5 keywords
    }

    /**
     * Find relevant files for a criterion
     * @param {string} criterion - Criterion text
     * @param {Array} changedFiles - List of changed files
     * @returns {Array} Relevant files
     */
    findRelevantFiles(criterion, changedFiles) {
        const keywords = this.extractKeywords(criterion.toLowerCase());
        const relevantFiles = [];

        for (const file of changedFiles) {
            const fileLower = file.toLowerCase();
            if (keywords.some(keyword => fileLower.includes(keyword))) {
                relevantFiles.push(file);
            }
        }

        return relevantFiles;
    }

    /**
     * Check implementation patterns in changed files
     * @param {string} criterion - Criterion text
     * @param {Array} changedFiles - Changed files
     * @returns {boolean} Whether patterns detected
     */
    checkImplementationPatterns(criterion, changedFiles) {
        const patterns = {
            'ui': ['component', 'view', 'template', 'style', 'css', 'tsx', 'jsx'],
            'api': ['endpoint', 'route', 'controller', 'service', 'api'],
            'test': ['test', 'spec', '.test.', '.spec.'],
            'documentation': ['readme', 'docs', '.md'],
            'configuration': ['config', 'settings', 'env'],
            'validation': ['validate', 'validator', 'check'],
            'security': ['auth', 'security', 'permission', 'access']
        };

        const criterionLower = criterion.toLowerCase();

        for (const [patternType, keywords] of Object.entries(patterns)) {
            if (keywords.some(keyword => criterionLower.includes(keyword))) {
                // Check if any changed files match this pattern
                if (changedFiles.some(file =>
                    keywords.some(kw => file.toLowerCase().includes(kw))
                )) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * Map agent results to acceptance criteria
     * @param {Object} agentResults - Results from all review agents
     * @param {Array} acceptanceCriteria - List of acceptance criteria text
     * @returns {Array} Verification results
     */
    mapAgentResultsToCriteria(agentResults, acceptanceCriteria) {
        const verificationResults = [];

        for (const criterionText of acceptanceCriteria) {
            const criterion = criterionText.toLowerCase();
            let completed = false;
            let details = "No evidence found";

            // Map common acceptance criteria patterns to agent results
            if (criterion.includes('todo') || criterion.includes('placeholder')) {
                const codeQualityResults = agentResults.codeQuality || {};
                completed = !codeQualityResults.todoComments || codeQualityResults.todoComments.length === 0;
                details = completed
                    ? "✅ Verified: No TODO comments found"
                    : `❌ Failed: ${codeQualityResults.todoComments?.length || 0} TODO comments found`;
            }
            else if (criterion.includes('security') || criterion.includes('credential') || criterion.includes('secret')) {
                const securityResults = agentResults.security || {};
                completed = !securityResults.criticalVulnerabilities || securityResults.criticalVulnerabilities.length === 0;
                details = completed
                    ? "✅ Verified: No critical security vulnerabilities"
                    : `❌ Failed: ${securityResults.criticalVulnerabilities?.length || 0} critical vulnerabilities`;
            }
            else if (criterion.includes('test') || criterion.includes('coverage')) {
                const testResults = agentResults.testCoverage || {};
                completed = testResults.coveragePercentage >= 80;
                details = `${completed ? '✅' : '❌'} Test coverage ${testResults.coveragePercentage || 0}%`;
            }
            else if (criterion.includes('documentation') || criterion.includes('readme')) {
                const docResults = agentResults.documentation || {};
                completed = docResults.completeness >= 80;
                details = completed
                    ? "✅ Verified: Documentation complete"
                    : "❌ Failed: Documentation incomplete";
            }
            else if (criterion.includes('error handling')) {
                const codeQualityResults = agentResults.codeQuality || {};
                completed = codeQualityResults.errorHandling >= 8;
                details = `${completed ? '✅' : '❌'} Error handling score ${codeQualityResults.errorHandling || 0}/10`;
            }
            else {
                // Generic check using pattern detection
                const keywords = this.extractKeywords(criterion);
                completed = this.checkGenericCriterion(agentResults, keywords);
                details = completed
                    ? "✅ Verified: Implementation patterns detected"
                    : "❌ Not verified: No evidence found";
            }

            verificationResults.push({
                text: criterionText,
                completed,
                details
            });
        }

        return verificationResults;
    }

    /**
     * Check generic criterion against agent results
     * @param {Object} agentResults - All agent results
     * @param {Array} keywords - Keywords to check
     * @returns {boolean} Whether criterion is met
     */
    checkGenericCriterion(agentResults, keywords) {
        const passedAgents = Object.values(agentResults).filter(result =>
            result.success && result.score >= 7
        ).length;

        const keywordMatches = Object.values(agentResults).some(result =>
            keywords.some(keyword =>
                JSON.stringify(result).toLowerCase().includes(keyword)
            )
        );

        return passedAgents >= 2 && keywordMatches;
    }

    /**
     * Generate base verification report
     * @param {string} workItemId - Work item ID
     * @param {Array} verificationResults - Results
     * @param {string} systemName - PM system name
     * @returns {string} Formatted report
     */
    generateBaseVerificationReport(workItemId, verificationResults, systemName = '') {
        const completedCount = verificationResults.filter(r => r.completed).length;
        const totalCount = verificationResults.length;
        const completionPercentage = totalCount > 0 ? (completedCount / totalCount * 100) : 0;

        let report = `## 🔍 Acceptance Criteria Verification Report

**Work Item**: ${workItemId}
**Completion**: ${completionPercentage.toFixed(1)}% (${completedCount}/${totalCount} criteria)

### Detailed Verification Results:

`;

        for (const criterion of verificationResults) {
            const statusIcon = criterion.completed ? "✅" : "❌";
            report += `**${statusIcon} ${criterion.text}**\n`;
            report += `   _${criterion.details}_\n\n`;
        }

        const systemInfo = systemName ? ` (${systemName} Integration)` : '';
        report += `
### Summary

This automated verification is based on:
- File changes in the PR
- PR description content
- Implementation pattern detection

**Note**: Manual review recommended for subjective criteria.

---
_🤖 Verified by Claude Code SubAgent${systemInfo}_
`;

        return report;
    }

    /**
     * Extract acceptance criteria from text (to be overridden by subclasses)
     * @param {string} text - Text containing criteria
     * @returns {Array} Array of criterion text strings
     */
    extractAcceptanceCriteria(text) {
        // This will be overridden by ADO and JIRA specific implementations
        throw new Error('extractAcceptanceCriteria must be implemented by subclass');
    }

    /**
     * Update criteria text with verification status (to be overridden)
     * @param {string} currentText - Current text with checkboxes
     * @param {Array} verificationResults - Array of {text, completed, details}
     * @returns {string} Updated text with status icons
     */
    updateCriteriaText(currentText, verificationResults) {
        // This will be overridden by ADO and JIRA specific implementations
        throw new Error('updateCriteriaText must be implemented by subclass');
    }
}

module.exports = { CheckboxUpdaterBase };