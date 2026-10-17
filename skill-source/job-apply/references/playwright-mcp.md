# Playwright MCP backend (default)

Prerequisite: the host exposes a working Playwright MCP server. Standard launch: `playwright-mcp` (MCP command `playwright-mcp`, arguments `[]`), installed and available on the agent's PATH. See [official setup](https://github.com/microsoft/playwright-mcp). Report unavailable tools or browser prerequisites; use terminal-browser only on explicit user selection.

Discover the exposed schemas; tool prefixes and parameters depend on the host and release. Use `browser_tabs` to select an application tab, `browser_navigate` to open the URL, and `browser_snapshot` to inspect fields. Use current snapshot references with `browser_fill_form`, `browser_type`, `browser_select_option`, and `browser_click`. Refresh snapshots after page changes and list/select tabs after redirects or popups.

Open the resume file chooser, then use `browser_file_upload` with the configured resume's absolute path accessible to the server. If inaccessible, pause for user upload or setup. Verify the filename and parsed fields.

Keep the current job's tab selected and preserve unrelated tabs. Follow the main skill's review, submission intent, and recovery rules, including after tool failures.
