# Vessel backend

Prerequisite: Vessel is running, and the host agent can reach its MCP server. The recommended stdio entry uses command `vessel-browser-mcp` with arguments `["--stdio"]`; its helper resolves local authentication. The browser executable alone does not expose tools to the agent. Do not print auth files or bearer tokens.

Discover the actual available tools and read their schemas. Use the tools for tab selection, navigation, content/form inspection, filling/selecting, file upload, clicking, and confirmation inspection. Tool names and upload support depend on the installed release; never invent a tool or assume that a text field can upload a file. If upload is unavailable, pause for manual upload.

Select a dedicated tab for the current application and maintain its ID throughout redirects. Inspect current form labels, types, required fields, choices, and actions before filling. Refresh extraction after changes. If screenshots are unavailable, use structured content and ask for help when the page cannot be interpreted reliably.

Use Vessel's visible approval UI when required. An undo/checkpoint cannot retract an application already sent to an employer. A failed tool response does not establish that a submit action failed. Follow the main skill's submission intent and recovery procedure.

Setup: [Vessel repository](https://github.com/unmodeled-tyler/vessel-browser). Configure MCP in the host agent; this skill does not edit that configuration.
