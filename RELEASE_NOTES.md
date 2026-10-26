# v4.0.4 — terminal tickets leave the open queue

Patch release. Ticket files now agree with the index after cancellation or
termination, operator-facing counts and messages describe what the tools
actually show, and On Board is ready for publication to the official MCP
Registry.

- **Canceled and terminated tickets are filed under `tickets/closed/`.** The
  index already recorded the right terminal state, but the Markdown file stayed
  in `tickets/`, which is documented as the open queue. New cancel and terminate
  operations now write the terminal record under `closed/`, remove the open
  copy, and carry any submission out of `tickets/review/`. The response names
  the final path.

- **The dashboard Tickets badge matches the ticket view.** The badge used to
  count only open tickets while the page showed every ticket. It now displays
  the number of rows in that view; open work still controls the hot styling.

- **The compaction measurement helper reports an empty cold set honestly.** It
  now lists every reason an entry can be exempt instead of claiming all entries
  are pinned or high-priority.

- **CI covers the missing root-level regression suites.** Hot/cold ranking,
  handoff pinning, and board-lock tests now run on every push and pull request.

- **Fresh installs keep a compatible MCP SDK.** The dependency now excludes
  MCP SDK 2.x, which removed the `mcp.server.fastmcp` import used by this
  release. Existing MCP SDK 1.x installations are unaffected.

- **Official MCP Registry metadata is included.** `server.json` describes the
  published PyPI package, `stdio` transport, project icon, source repository,
  and required `AGENT_PROJECT_DIR` filepath. The README carries the hidden PyPI
  ownership marker. These are discovery and ownership metadata only; they do
  not change the server's tools or runtime behavior.

Upgrading is a drop-in: there is no board schema migration and no new runtime
dependency. Ticket-file cleanup is forward-only; terminal files left in the
open queue by an older release are not moved automatically.
