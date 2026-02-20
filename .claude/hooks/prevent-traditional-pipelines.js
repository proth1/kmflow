#!/usr/bin/env node

/**
 * Claude Code Hook: Prevent Traditional Pipeline Creation
 * ========================================================
 * Claude Code IS the CI/CD execution engine. It replaces traditional
 * pipeline tools (GitHub Actions, Jenkins, etc.) entirely.
 *
 * Use `.claude/agents/pipeline-orchestrator.md` for CI/CD.
 */

const PIPELINE_PATTERNS = [
  {
    pattern: /\.github\/workflows\/.*\.yml$/,
    message: 'GitHub Actions workflow detected. Use Claude Code pipeline-orchestrator instead.'
  },
  {
    pattern: /azure-pipelines.*\.yml$/,
    message: 'Azure DevOps pipeline detected. Use Claude Code pipeline-orchestrator instead.'
  },
  {
    pattern: /Jenkinsfile/,
    message: 'Jenkins pipeline detected. Use Claude Code pipeline-orchestrator instead.'
  },
  {
    pattern: /\.gitlab-ci\.yml$/,
    message: 'GitLab CI detected. Use Claude Code pipeline-orchestrator instead.'
  },
  {
    pattern: /\.circleci\/config\.yml$/,
    message: 'CircleCI detected. Use Claude Code pipeline-orchestrator instead.'
  }
];

function checkFile(filepath) {
  for (const check of PIPELINE_PATTERNS) {
    if (check.pattern.test(filepath)) {
      return {
        file: filepath,
        message: check.message
      };
    }
  }
  return null;
}

function preventTraditionalPipelines(files) {
  const violations = files.map(checkFile).filter(v => v !== null);

  if (violations.length > 0) {
    console.error('\nARCHITECTURAL VIOLATION: Traditional CI/CD Pipeline Detected!\n');
    console.error('='.repeat(70));

    violations.forEach(v => {
      console.error(`\nFile: ${v.file}`);
      console.error(`   ${v.message}`);
    });

    console.error('\n' + '='.repeat(70));
    console.error('\nClaude Code IS the CI/CD execution engine.');
    console.error('Use: claude -a pipeline-orchestrator\n');

    return false;
  }

  return true;
}

module.exports = { checkFile, preventTraditionalPipelines };

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log('Usage: prevent-traditional-pipelines.js <file1> [file2] ...');
    process.exit(1);
  }

  const success = preventTraditionalPipelines(args);
  process.exit(success ? 0 : 1);
}
