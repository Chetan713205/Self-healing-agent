# Phase 1 — Set up Cursor Agent CLI

## Step 1. Prepare your Windows environment

Since you're using Windows, open PowerShell and ensure you have:

- Python 3.11 or newer.
- Git for Windows.
- Cursor installed and a Cursor account.
- Access to the Cursor plan/features you intend to use.

You do not need to install Ollama or download another model.

## Step 2. Install Cursor CLI

Open PowerShell and run the official Windows installer command:

```
irm 'https://cursor.com/install?win32=true' | iex
```

The current Cursor documentation uses the `agent` CLI command. Some installations or older instructions use `cursor-agent`, so use the executable name actually installed on your machine.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://cursor.com\&sz=32)

Cursor Docs

+1



Verify the installation by checking the CLI version and help output.

## Step 3. Authenticate without an external model API key

Run:

```
agent login
```

Complete the authentication flow using your Cursor account. Then verify the login status:

```
agent status
```

Important distinction: you are using Cursor's hosted coding-agent capability through the CLI, not calling the OpenAI, Anthropic, or another model provider's API directly. You don't need a separate provider API key for this workflow. Cursor account access, plan limits, and network connectivity still apply.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://prod.cursor.com\&sz=32)

Cursor Docs

+1



## Step 4. Test the coding agent independently

Create a project folder, navigate into it, and initialize a Git repository.

Start Cursor Agent in interactive mode:

```
agent
```

Ask it to inspect the project and propose a design for a FastAPI self-healing API agent. Initially, instruct it not to modify any files.

Then try a planning request:

```
agent --mode=plan
```

If your installed version uses different flags, check its help output.

Finally, test non-interactive mode:

```
agent -p "Inspect this repository and summarize its structure. Do not modify any files." --output-format text
```

The `-p` mode is useful because it allows you to invoke the coding agent from a terminal or automation script. Be aware that non-interactive mode has write and shell-execution capabilities, so use a disposable Git repository and review permissions carefully.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.cursor.com\&sz=32)

Using CLI

+1



Checkpoint: Cursor CLI works, your account is authenticated, and you can invoke the coding agent without supplying a separate model-provider API key.

# Phase 2 — Build the sample API application

## Step 5. Ask Cursor to create the application foundation

Use the Cursor CLI in your project directory. Ask it to create a small FastAPI application with three related business functions:

- Orders API.
- Invoices API.
- Revenue reports API.

Have it include realistic service dependencies so a change in one function can affect the other endpoints.

For example, invoice calculations depend on order totals, while revenue reports aggregate invoice amounts.

Ask Cursor to create:

- The FastAPI application.
- Request and response schemas.
- A machine-readable OpenAPI contract.
- Unit tests for the business logic.
- API integration tests.
- A README explaining how to start the application and run tests.

Keep this application deliberately small. You want to demonstrate the self-healing architecture, not build an entire enterprise platform.

## Step 6. Run the baseline tests

Before introducing any agent logic:

1. Install the project dependencies in a virtual environment.
2. Start the FastAPI application locally.
3. Run all unit and integration tests.
4. Check the API documentation at the application's OpenAPI documentation page.
5. Save the initial test results.

At this point, all tests should pass.

This baseline is essential: if your original application is already broken, you cannot credibly demonstrate that the agent repaired it.

## Step 7. Add controlled failure scenarios

Ask Cursor to create a few reproducible bug-injection scenarios.

Start with these:

| Scenario | Injected defect                                                | Expected detection                                     |
| -------- | -------------------------------------------------------------- | ------------------------------------------------------ |
| A        | Rename the order response field `total` to `amount`            | Contract violation                                     |
| B        | Change order-total calculation logic                           | Incorrect invoice values or failed business assertions |
| C        | Change a shared service in a way that breaks revenue reporting | Downstream regression                                  |

Each scenario should have a known expected failure and a known correct outcome.

Do not let your bug injector modify the main branch silently. Use a dedicated demo branch or a disposable Git worktree.

Checkpoint: You have a functioning application, passing baseline tests, and reproducible bugs.

# Phase 3 — Build your MCP server

## Step 8. Decide what MCP will do

MCP is the bridge between Cursor Agent and the tools your project provides. Cursor Agent is the reasoning and coding component; your MCP server exposes controlled operations it can invoke. Cursor supports local MCP servers through project configuration.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://prod.cursor.com\&sz=32)

Cursor Docs

+1



Your MCP server should expose tools such as these:

| MCP tool                  | Responsibility                                                            |
| ------------------------- | ------------------------------------------------------------------------- |
| `check_api_health`        | Call the local API and compare responses with the contract                |
| `get_contract_violations` | Return missing fields, incorrect types, and schema mismatches             |
| `get_recent_changes`      | Retrieve recent Git commits and diffs                                     |
| `analyze_impact`          | Identify potentially affected endpoints and relevant tests                |
| `run_targeted_tests`      | Run selected tests against the suspected impact area                      |
| `run_full_tests`          | Run the complete unit and integration test suite                          |
| `get_failure_evidence`    | Collect test failures and relevant application logs                       |
| `submit_fix_report`       | Generate the diagnosis, proposed patch summary, and verification evidence |

For a controlled POC, these tools are enough. You do not need a separate MCP function for every individual endpoint or test.

## Step 9. Create the MCP server project structure

Ask Cursor to organize the project into separate responsibilities:

- `app/` — the FastAPI application and business logic.
- `contracts/` — the expected API schemas.
- `tests/` — unit, contract, and integration tests.
- `mcp_server/` — the MCP server and tool implementations.
- `reports/` — generated diagnostic and repair reports.
- `.cursor/` — Cursor project configuration.

Keep the MCP server separate from the application's business logic. This makes it easier to replace the sample application with another system later.

## Step 10. Implement the MCP tools in stages

Do not ask Cursor to implement every tool and the entire repair loop in one giant task.

Build and verify them in this order:

1. Health check: the MCP tool can call your running API.
2. Contract validation: the tool can detect a broken response.
3. Git inspection: the tool can retrieve a recent change and its diff.
4. Impact analysis: the tool can identify related endpoints and relevant tests.
5. Test execution: the tool can run selected tests and return structured results.
6. Report generation: the tool can save a report with evidence and status.

For impact analysis, start with an explicit dependency map between services, endpoints, and tests. You can later improve it with static code analysis and observed test coverage.

Avoid relying on an LLM's unsupported guess about which endpoints are affected. The agent can interpret the evidence, but the underlying dependency information should be grounded in your code and test suite.

## Step 11. Connect MCP to Cursor CLI

Create the project-level MCP configuration at:

`.cursor/mcp.json`

Register your local MCP server using the appropriate Python command and arguments. The configuration should point to the server's actual location inside your project.

For a local Python server, use the stdio transport initially. This is simpler than deploying a remote MCP service and is sufficient for a local demo. Cursor's CLI can use the same MCP configuration as the editor.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://prod.cursor.com\&sz=32)

Cursor Docs

+1



Then:

1. Save the configuration.
2. Restart or reload the relevant Cursor agent session if needed.
3. List the configured MCP servers.
4. Confirm your server appears as connected.
5. List the tools exposed by your server.
6. Test each tool individually before attempting autonomous repair.

Useful CLI commands, depending on your installed executable, include:

- `agent mcp list`

If the server does not connect, inspect the MCP logs and verify the Python environment and server path.

Critical detail: for a stdio server, keep diagnostic logging off standard output. Unexpected output can interfere with the MCP protocol.

# Phase 4 — Connect the agent to testing and code repair

## Step 12. Make the MCP server responsible for verification

This is an important architectural decision.

Do not let the LLM decide by itself whether its patch is correct. The MCP server should run the checks and return the actual results.

Your test workflow should be:

Cursor Agent

Requests diagnosis, impact analysis, and a proposed repair

MCP tools

Check API contract → inspect Git diff → identify affected tests

Isolated repair workspace

Cursor edits the code in a dedicated Git worktree

Independent verification

MCP runs contract tests, targeted regression tests, then the full test suite

All pass

Save evidence and prepare the patch for human approval

Any fail

Return the failure evidence to Cursor for another attempt, or stop safely

## Step 13. Implement the impact-based test selection

This is the feature that directly addresses your manager's feedback.

When a code change occurs, the system should:

1. Identify which files and functions changed.
2. Map those changes to dependent services and API endpoints.
3. Find tests that exercise those components.
4. Prioritize tests based on dependency reach, business criticality, and change risk.
5. Run the selected tests first.
6. Run the complete suite before accepting a patch.

For the demo, show the difference between running all 100 hypothetical tests and running a smaller, relevant subset first. Use your actual test results rather than inventing time savings.

Do not make the mistake of permanently skipping the full test suite. Impact analysis helps prioritize testing; it does not prove that unrelated functionality cannot regress.

## Step 14. Enable Cursor Agent to use the MCP tools

Now ask Cursor CLI to perform a complete diagnosis-and-repair task, explicitly instructing it to use your registered MCP tools.

The agent should:

- Call `check_api_health`.
- Call `get_contract_violations`.
- Inspect the recent Git diff.
- Call `analyze_impact`.
- Run relevant tests to establish the failure.
- Make the smallest justified repair in the isolated workspace.
- Call the verification tools.
- Produce a report with the test results and patch summary.

Use interactive mode for the first few runs, so you can inspect tool calls and approve commands. Only move to headless mode after the workflow is reliable.

Cursor CLI supports MCP tools in both interactive and non-interactive workflows.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.cursor.com\&sz=32)

Using CLI

+1



## Step 15. Add bounded repair attempts

Your repair loop should have a strict maximum of three attempts.

| Attempt       | Action                                                                        |
| ------------- | ----------------------------------------------------------------------------- |
| 1             | Diagnose the failure and generate a minimal patch.                            |
| 2             | If verification fails, examine the new failure evidence and revise the patch. |
| 3             | Make one final correction and run verification again.                         |
| After failure | Stop, discard the unaccepted patch, and generate an escalation report.        |

Each attempt must use fresh verification results. Do not treat a previous passing test as proof that the latest patch works.

Also include a time limit, a maximum patch size, and restrictions on which files the agent may modify. These guardrails help prevent a repair loop from making progressively larger and less reliable changes.

## Step 16. Add human approval

Once all tests pass, the agent should create a repair report containing:

- Original failure.
- Root-cause hypothesis and supporting evidence.
- Files and functions changed.
- Before-and-after behavior.
- Contract test results.
- Targeted regression test results.
- Full-suite results.
- Remaining risks and approval status.

The system should produce a proposed patch or pull request for review. It must not automatically merge to the main branch or deploy to production.

For the POC, a generated Markdown report and a patch in a dedicated branch are sufficient.

# Phase 5 — Run the complete end-to-end demo

## Step 17. Demonstrate three scenarios

## Demo checklist

0 of 3 tested

Successful repair

Inject a response-field rename and demonstrate detection, diagnosis, repair, and passing regression tests.

Regression prevented

Introduce a change where the initial repair appears correct but breaks invoice or reporting behavior. Show the verification gate rejecting it.

Safe escalation

Inject a failure that the agent cannot reliably resolve. Demonstrate bounded retries, sandbox cleanup, and a diagnostic report.

For every scenario, preserve the terminal output, test report, Git diff, and final agent report. These become the evidence for your technical manager.

## Step 18. Automate the complete workflow through CLI

After the interactive workflow succeeds consistently, create a single orchestration entry point that:

1. Creates an isolated workspace.
2. Starts the application and checks its baseline.
3. Applies a selected demo failure.
4. Invokes Cursor Agent CLI in non-interactive mode.
5. Allows the agent to use the configured MCP tools.
6. Collects test results and the proposed patch.
7. Accepts the patch only when independent verification succeeds.
8. Generates the final report and cleans up temporary resources.

The orchestration entry point should control the workflow; the MCP server should provide the tools; Cursor Agent should reason about and implement the repair.

This separation matters. MCP is not itself the autonomous agent, and a successful CLI invocation does not mean the repair has been verified.

Initially, run the orchestration manually from PowerShell. Do not integrate it into an actual CI/CD pipeline until the local workflow is repeatable.

## Step 19. Prepare the impact report

Capture these measurements from your demo:

- Number of injected failures.
- Number correctly detected.
- Number successfully repaired and independently verified.
- Number of incorrect patches rejected.
- Number of failures safely escalated.
- Average diagnosis and repair time.
- Number of tests selected versus the full suite.
- Human intervention required.

State clearly that these are POC results and explain the number and type of test scenarios. Do not present a small synthetic benchmark as proof of production reliability.

# Phase 6 — Make it scalable beyond your demo

Once the local POC works, document how each component can be replaced or extended.

| POC component        | Possible future extension                                     |
| -------------------- | ------------------------------------------------------------- |
| Local FastAPI app    | Enterprise services in a staging environment                  |
| Static API contracts | Versioned contracts and compatibility policies                |
| Basic dependency map | Static analysis, coverage data, and service dependency graphs |
| Local MCP server     | Authenticated, centrally managed MCP service                  |
| Local test runner    | Distributed test execution                                    |
| Markdown report      | Audit dashboard and pull-request integration                  |
| Manual trigger       | Event-driven invocation from development workflows            |

Treat these as future extensions, not requirements for your first demo. You can also extend the same pattern to database schema changes, data pipeline regressions, or other engineering workflows.

## Final implementation order

Follow this sequence and do not jump ahead:

1 Install and authenticate Cursor CLI

2 Build the sample FastAPI application

3 Create contracts and baseline tests

4 Implement reproducible failure scenarios

5 Build and test the MCP server

6 Connect MCP to Cursor CLI

7 Implement impact-based test selection

8 Enable isolated code repair

9 Add independent verification and bounded retries

10 Add reporting and human approval

11 Automate the three demo scenarios

12 Measure results and prepare the presentation