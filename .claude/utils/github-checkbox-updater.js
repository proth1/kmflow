/**
 * GitHub Issues Checkbox Updater
 *
 * GitHub Issues specific checkbox update functionality
 * Updates acceptance criteria checkboxes in issue body when tests pass/fail
 */

const { CheckboxUpdaterBase } = require('./checkbox-updater-base.js');
const { spawn } = require('child_process');

class GitHubCheckboxUpdater extends CheckboxUpdaterBase {
    constructor() {
        super();
        this.name = "GitHubCheckboxUpdater";
    }

    /**
     * Get repository from config or environment
     * @returns {string} Repository in OWNER/REPO format
     */
    getRepository() {
        // Try environment variable first
        if (process.env.GITHUB_REPOSITORY) {
            return process.env.GITHUB_REPOSITORY;
        }

        // Try to read from config
        const fs = require('fs');
        const yaml = require('yaml');
        const configPath = '.claude/config/project-management.yaml';

        if (fs.existsSync(configPath)) {
            const config = yaml.parse(fs.readFileSync(configPath, 'utf8'));
            return config.repository || '';
        }

        return '';
    }

    /**
     * Extract acceptance criteria from GitHub issue body
     * @param {string} text - Markdown text containing criteria
     * @returns {Array} Array of criterion text strings
     */
    extractAcceptanceCriteria(text) {
        const criteria = [];
        const lines = text.split('\n');
        let inAcceptanceCriteria = false;

        for (const line of lines) {
            const trimmed = line.trim();

            // Detect acceptance criteria section
            if (trimmed.match(/^##?\s*acceptance\s*criteria/i)) {
                inAcceptanceCriteria = true;
                continue;
            }

            // End section on next heading
            if (inAcceptanceCriteria && trimmed.match(/^##/)) {
                inAcceptanceCriteria = false;
                continue;
            }

            // Only extract within acceptance criteria section
            if (!inAcceptanceCriteria) continue;

            // Match markdown checkbox patterns
            const checkboxMatch = trimmed.match(/^-\s*\[\s*[x ]?\s*\]\s*(.+)$/i);
            if (checkboxMatch) {
                criteria.push(checkboxMatch[1].trim());
                continue;
            }

            // Match Gherkin Given/When/Then patterns
            const gherkinMatch = trimmed.match(/^(Given|When|Then|And|But)\s+(.+)$/i);
            if (gherkinMatch) {
                criteria.push(`${gherkinMatch[1]} ${gherkinMatch[2].trim()}`);
                continue;
            }

            // Match numbered items
            const numberedMatch = trimmed.match(/^\d+\.\s*(.+)$/);
            if (numberedMatch) {
                criteria.push(numberedMatch[1].trim());
            }
        }

        return criteria;
    }

    /**
     * Update GitHub issue body with verification status
     * @param {string} currentText - Current markdown text with checkboxes
     * @param {Array} verificationResults - Array of {text, completed, details}
     * @returns {string} Updated markdown text with status
     */
    updateCriteriaText(currentText, verificationResults) {
        let updatedText = currentText;

        for (const criterion of verificationResults) {
            const criterionText = criterion.text.trim();

            if (criterion.completed) {
                // Update to checked status
                const patterns = [
                    // Markdown checkbox patterns
                    { from: `- [ ] ${criterionText}`, to: `- [x] ${criterionText}` },
                    { from: `- [] ${criterionText}`, to: `- [x] ${criterionText}` },
                    // Already checked - keep as is
                    { from: `- [x] ${criterionText}`, to: `- [x] ${criterionText}` },
                    { from: `- [X] ${criterionText}`, to: `- [x] ${criterionText}` }
                ];

                for (const pattern of patterns) {
                    if (updatedText.includes(pattern.from)) {
                        updatedText = updatedText.replace(pattern.from, pattern.to);
                        break;
                    }
                }
            } else {
                // Update to unchecked status
                const patterns = [
                    { from: `- [x] ${criterionText}`, to: `- [ ] ${criterionText}` },
                    { from: `- [X] ${criterionText}`, to: `- [ ] ${criterionText}` },
                    { from: `- [ ] ${criterionText}`, to: `- [ ] ${criterionText}` }
                ];

                for (const pattern of patterns) {
                    if (updatedText.includes(pattern.from)) {
                        updatedText = updatedText.replace(pattern.from, pattern.to);
                        break;
                    }
                }
            }
        }

        return updatedText;
    }

    /**
     * Update GitHub issue with verification results
     * @param {string} issueNumber - GitHub issue number (e.g., "123" or "#123")
     * @param {Array} verificationResults - Verification results
     * @returns {boolean} Success status
     */
    async updateGitHubIssue(issueNumber, verificationResults) {
        try {
            // Normalize issue number (remove # prefix if present)
            const normalizedNumber = issueNumber.replace(/^#/, '');
            const repo = this.getRepository();

            console.log(`Updating GitHub issue #${normalizedNumber} with verification results...`);

            if (!repo) {
                console.error('ERROR: No repository configured');
                return false;
            }

            // Get current issue body
            const issueBody = await this.getIssueBody(normalizedNumber, repo);
            if (!issueBody) {
                console.error(`ERROR: Could not fetch issue #${normalizedNumber}`);
                return false;
            }

            // Update the body with verification results
            const updatedBody = this.updateCriteriaText(issueBody, verificationResults);

            // Update the issue
            return await this.setIssueBody(normalizedNumber, repo, updatedBody);

        } catch (error) {
            console.error(`Error updating GitHub issue: ${error}`);
            return false;
        }
    }

    /**
     * Get issue body via gh CLI
     * @param {string} issueNumber - Issue number
     * @param {string} repo - Repository (OWNER/REPO)
     * @returns {Promise<string>} Issue body
     */
    async getIssueBody(issueNumber, repo) {
        return new Promise((resolve) => {
            const process = spawn('gh', ['issue', 'view', issueNumber, '--repo', repo, '--json', 'body', '-q', '.body'], {
                stdio: ['pipe', 'pipe', 'pipe']
            });

            let stdout = '';
            let stderr = '';

            process.stdout.on('data', (data) => stdout += data.toString());
            process.stderr.on('data', (data) => stderr += data.toString());

            process.on('close', (code) => {
                if (code === 0) {
                    resolve(stdout.trim());
                } else {
                    console.error(`gh issue view failed: ${stderr}`);
                    resolve(null);
                }
            });

            // Set timeout
            setTimeout(() => {
                process.kill();
                resolve(null);
            }, 10000);
        });
    }

    /**
     * Set issue body via gh CLI
     * @param {string} issueNumber - Issue number
     * @param {string} repo - Repository (OWNER/REPO)
     * @param {string} body - New issue body
     * @returns {Promise<boolean>} Success status
     */
    async setIssueBody(issueNumber, repo, body) {
        return new Promise((resolve) => {
            const process = spawn('gh', ['issue', 'edit', issueNumber, '--repo', repo, '--body', body], {
                stdio: ['pipe', 'pipe', 'pipe']
            });

            let stderr = '';

            process.stderr.on('data', (data) => stderr += data.toString());

            process.on('close', (code) => {
                if (code === 0) {
                    console.log(`Updated GitHub issue #${issueNumber}`);
                    resolve(true);
                } else {
                    console.error(`gh issue edit failed: ${stderr}`);
                    resolve(false);
                }
            });

            // Set timeout
            setTimeout(() => {
                process.kill();
                resolve(false);
            }, 10000);
        });
    }

    /**
     * Add verification comment to issue
     * @param {string} issueNumber - Issue number
     * @param {Array} verificationResults - Verification results
     * @returns {Promise<boolean>} Success status
     */
    async addVerificationComment(issueNumber, verificationResults) {
        try {
            const normalizedNumber = issueNumber.replace(/^#/, '');
            const repo = this.getRepository();

            if (!repo) {
                console.error('ERROR: No repository configured');
                return false;
            }

            const report = this.generateVerificationReport(issueNumber, verificationResults);

            return new Promise((resolve) => {
                const process = spawn('gh', ['issue', 'comment', normalizedNumber, '--repo', repo, '--body', report], {
                    stdio: ['pipe', 'pipe', 'pipe']
                });

                let stderr = '';

                process.stderr.on('data', (data) => stderr += data.toString());

                process.on('close', (code) => {
                    if (code === 0) {
                        console.log(`Added verification comment to issue #${normalizedNumber}`);
                        resolve(true);
                    } else {
                        console.error(`gh issue comment failed: ${stderr}`);
                        resolve(false);
                    }
                });

                // Set timeout
                setTimeout(() => {
                    process.kill();
                    resolve(false);
                }, 10000);
            });

        } catch (error) {
            console.error(`Error adding comment: ${error}`);
            return false;
        }
    }

    /**
     * Generate GitHub verification report
     * @param {string} issueNumber - Issue number
     * @param {Array} verificationResults - Verification results
     * @returns {string} Formatted report
     */
    generateVerificationReport(issueNumber, verificationResults) {
        return this.generateBaseVerificationReport(issueNumber, verificationResults, 'GitHub Issues');
    }

    /**
     * Update PR description with acceptance criteria status
     * @param {string} prNumber - PR number
     * @param {Array} verificationResults - Verification results
     * @returns {Promise<boolean>} Success status
     */
    async updatePRDescription(prNumber, verificationResults) {
        try {
            const normalizedNumber = prNumber.replace(/^#/, '');
            const repo = this.getRepository();

            console.log(`Updating PR #${normalizedNumber} with verification results...`);

            if (!repo) {
                console.error('ERROR: No repository configured');
                return false;
            }

            // Get current PR body
            const prBody = await this.getPRBody(normalizedNumber, repo);
            if (!prBody) {
                console.error(`ERROR: Could not fetch PR #${normalizedNumber}`);
                return false;
            }

            // Generate verification section
            const report = this.generateVerificationReport(`PR #${normalizedNumber}`, verificationResults);

            // Check if verification section already exists
            const verificationSectionRegex = /## .*Acceptance Criteria Verification Report[\s\S]*?---\s*_.*Verified by Claude Code SubAgent.*_/;

            let updatedBody;
            if (prBody.match(verificationSectionRegex)) {
                // Replace existing section
                updatedBody = prBody.replace(verificationSectionRegex, report);
            } else {
                // Add new section at the end
                updatedBody = prBody + '\n\n' + report;
            }

            return await this.setPRBody(normalizedNumber, repo, updatedBody);

        } catch (error) {
            console.error(`Error updating PR description: ${error}`);
            return false;
        }
    }

    /**
     * Get PR body via gh CLI
     * @param {string} prNumber - PR number
     * @param {string} repo - Repository (OWNER/REPO)
     * @returns {Promise<string>} PR body
     */
    async getPRBody(prNumber, repo) {
        return new Promise((resolve) => {
            const process = spawn('gh', ['pr', 'view', prNumber, '--repo', repo, '--json', 'body', '-q', '.body'], {
                stdio: ['pipe', 'pipe', 'pipe']
            });

            let stdout = '';
            let stderr = '';

            process.stdout.on('data', (data) => stdout += data.toString());
            process.stderr.on('data', (data) => stderr += data.toString());

            process.on('close', (code) => {
                if (code === 0) {
                    resolve(stdout.trim());
                } else {
                    console.error(`gh pr view failed: ${stderr}`);
                    resolve(null);
                }
            });

            setTimeout(() => {
                process.kill();
                resolve(null);
            }, 10000);
        });
    }

    /**
     * Set PR body via gh CLI
     * @param {string} prNumber - PR number
     * @param {string} repo - Repository (OWNER/REPO)
     * @param {string} body - New PR body
     * @returns {Promise<boolean>} Success status
     */
    async setPRBody(prNumber, repo, body) {
        return new Promise((resolve) => {
            const process = spawn('gh', ['pr', 'edit', prNumber, '--repo', repo, '--body', body], {
                stdio: ['pipe', 'pipe', 'pipe']
            });

            let stderr = '';

            process.stderr.on('data', (data) => stderr += data.toString());

            process.on('close', (code) => {
                if (code === 0) {
                    console.log(`Updated PR #${prNumber}`);
                    resolve(true);
                } else {
                    console.error(`gh pr edit failed: ${stderr}`);
                    resolve(false);
                }
            });

            setTimeout(() => {
                process.kill();
                resolve(false);
            }, 10000);
        });
    }

    /**
     * Update issue labels based on verification results
     * @param {string} issueNumber - Issue number
     * @param {Array} verificationResults - Verification results
     * @returns {Promise<boolean>} Success status
     */
    async updateIssueLabels(issueNumber, verificationResults) {
        try {
            const normalizedNumber = issueNumber.replace(/^#/, '');
            const repo = this.getRepository();

            if (!repo) {
                console.error('ERROR: No repository configured');
                return false;
            }

            const completedCount = verificationResults.filter(r => r.completed).length;
            const totalCount = verificationResults.length;
            const allComplete = completedCount === totalCount && totalCount > 0;

            // Update labels based on completion
            const labelsToAdd = allComplete ? ['cdd:verified'] : [];
            const labelsToRemove = allComplete ? ['cdd:evidence-required'] : [];

            if (labelsToAdd.length > 0) {
                await this.executeGh(['issue', 'edit', normalizedNumber, '--repo', repo,
                    '--add-label', labelsToAdd.join(',')]);
            }

            if (labelsToRemove.length > 0) {
                await this.executeGh(['issue', 'edit', normalizedNumber, '--repo', repo,
                    '--remove-label', labelsToRemove.join(',')]);
            }

            return true;

        } catch (error) {
            console.error(`Error updating labels: ${error}`);
            return false;
        }
    }

    /**
     * Execute gh CLI command
     * @param {Array} args - Command arguments
     * @returns {Promise<boolean>} Success status
     */
    async executeGh(args) {
        return new Promise((resolve) => {
            const process = spawn('gh', args, {
                stdio: ['pipe', 'pipe', 'pipe']
            });

            process.on('close', (code) => {
                resolve(code === 0);
            });

            setTimeout(() => {
                process.kill();
                resolve(false);
            }, 10000);
        });
    }
}

module.exports = { GitHubCheckboxUpdater };
