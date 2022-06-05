// derived from https://github.com/education/autograding/blob/1d058ce58864938499105ab5cd1c941651ce7e27/src/output.ts
module.exports = async ({github, context, core}, points) => {
    // Fetch the workflow run
    const workflowRunResponse = await github.rest.actions.getWorkflowRun({
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: context.runId,
    })
    const checkSuiteUrl = workflowRunResponse.data.check_suite_url
    const checkSuiteId = parseInt(checkSuiteUrl.match(/[0-9]+$/)[0], 10)
    const checkRunsResponse = await github.rest.checks.listForSuite({
      owner: context.repo.owner,
      repo: context.repo.repo,
      check_name: 'Autograding',
      check_suite_id: checkSuiteId,
    })
    const checkRun = checkRunsResponse.data.total_count === 1 && checkRunsResponse.data.check_runs[0]
    if (!checkRun) core.error("Oh no");
    // Update the checkrun, we'll assign the title, summary and text even though we expect
    // the title and summary to be overwritten by GitHub Actions (they are required in this call)
    // We'll also store the total in an annotation to future-proof
    const text = `Points ${points}`;
    // Unlike `education/autograding`, we do not discard the previous annotations
    let annotations = await github.rest.checks.listAnnotations({
      owner: context.repo.owner,
      repo: context.repo.repo,
      check_run_id: checkRun.id
    }).data;
    annotations.splice(0, 0, {
      // Using the `.github` path is what education/autograding does
      path: '.github',
      start_line: 1,
      end_line: 1,
      annotation_level: 'notice',
      message: text,
      title: 'Autograding complete',
    });
    await github.rest.checks.update({
      owner: context.repo.owner,
      repo: context.repo.repo,
      check_run_id: checkRun.id,
      output: {
        title: 'Autograding',
        summary: text,
        text: text,
        annotations: annotations,
      },
    })
  }