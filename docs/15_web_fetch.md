# 15. Web fetch (D-238)

**Status:** DERIVED. Built and verified (unit, mutation, a real-network opt-in suite and one real end-to-end run — see decisions.md D-238 for what was and was not verified). No contract, agent, runtime or API schema change.

## 15.1 What it is

One tool, `web/fetch`, that lets a mission read the public web pages its goal names. It implements the existing `ToolPort` (`eidos.agents.tool`) in a new package, `eidos.tools`, and is reached through the V1.2 tool gate unchanged: pinned allowlist entry, deterministic admission, a per-plan call budget, recorded call facts, and each page stored as its own citable artifact (`tool:web/fetch:<args digest>:<host>-<hash>`). It is **not** an agent, a plan step, an MCP server or a model.

It exists only where a deployer lists the `web_fetch` action in `EIDOS_ALLOWED_ACTIONS`; a mission may use it only if it lists the same action, has a `max_tool_calls` budget and autonomy of at least 1 (read-only). Any of those missing is a recorded denial and nothing is fetched.

## 15.2 What a call does

The Research agent calls its tool once per run with the **goal text** as `query` (unchanged). The adapter reads the `https` addresses **written in that goal** by a fixed pattern and fetches exactly those:

- no address: a real, empty answer; no network is touched;
- more than three, or any one that cannot be fetched: a typed failure naming the address (all-or-nothing, so a page is never silently left out of the evidence);
- each page becomes readable text — title, meta description and visible text for HTML (scripts, styles and markup removed), the text itself for plain text, JSON, XML, CSS and CSV — headed by the address it came from. A page that builds itself with JavaScript says so: EIDOS reads what the server sent and does not run scripts or draw the page.

**Addresses inside a fetched page are never followed.** A page is data, never an instruction (invariant 3).

## 15.3 The security rules (`eidos.tools.safe_https`)

A URL a user types must not be able to reach this deployment's own network. Each rule is a refusal, not a repair, and applies to the URL and to every redirect it leads to:

1. `https` only, the standard port only, no user name or password in the address.
2. A real public host name only. An IP address in any spelling (`127.0.0.1`, `2130706433`, `0x7f.1`, `[::1]`), a single-word name, and local-only suffixes (`.local`, `.internal`, `.localhost`, `.home.arpa`, ...) are refused.
3. The name is resolved once and **every** address must be public (not loopback, private, link-local, carrier-grade NAT, multicast, reserved, or an IPv4-mapped / 6to4 / Teredo / reserved form of one). A NAT64 address (`64:ff9b::/96`, what a DNS64 network returns for an IPv4-only host) is judged by the IPv4 address inside it.
4. The connection goes to the address that was just checked, not to the name; TLS verifies the certificate against the name. There is no second lookup, so DNS rebinding has no window.
5. Redirects are followed by hand, at most three, each revalidated from rule 1.
6. One deadline covers DNS, every connection and every read; the body is read in chunks up to 512 KB and a larger page is refused, never truncated; nothing is decompressed (`Accept-Encoding: identity`; a compressed answer is refused); a non-text type is refused from its headers without downloading the body.
7. Only `GET`, with no cookie, credential or caller-supplied header; no proxy setting is read.

The result of every page together is bounded by the allowlist entry (48 KB of text, provisional) and is refused whole if larger.

## 15.4 What it deliberately does not do

It does not render a page, take a screenshot, run JavaScript, log in, search the web, crawl, honour `robots.txt`, cache, or judge a page's quality. A model reading the text can describe it; EIDOS records that as the model's output, not a measurement (invariants 13, 17; D-146).

## 15.5 Operating it

- **Turn it on:** add `web_fetch` to `EIDOS_ALLOWED_ACTIONS` (comma separated). `render.yaml` does. Remove it to turn the tool off; missions that name it are then refused at creation (`invalid_spec`).
- **Egress:** the backend needs outbound HTTPS and DNS. Its own database and the Groq API are reached the same way.
- **Limits that remain:** no per-user rate limit or quota (D-233); a mission may fetch at most three pages per tool call and Research makes one call per plan attempt, so the bound on outbound requests is the per-tenant active-run cap and the queue. A free-tier host can take up to the 45-second call deadline to wake. The 48 KB text bound also keeps a fetched page inside a hosted model's per-minute token allowance.
- **Reading what was read:** the mission's Evidence section lists each cited page as a *Web page* with the text EIDOS read from it. The audit still calls it "not evidence" — it was fetched, not retrieved from a knowledge base.
