# Working rules for Claude in this repository

These rules come from the repository owner and apply to every session.

## 1. No changes without confirmation
- Do not change anything (code, config, docs, Notion pages, GitHub settings) until the owner has explicitly confirmed that specific change.
- Before each change, show exactly what will change and where, then wait for a clear "yes".
- One confirmation covers only the change it was given for; it does not carry over to later changes.

## 2. Every repository change goes through a pull request
- Never commit or push directly to `main`.
- Create a branch per change, commit, push, and open a pull request with a clear description:
  - **What** changed (files and summary)
  - **Why** it changed
  - **How to test / verify** it
- Do not merge pull requests; the owner merges.

## 3. Notion workshop page — "jmeter" section
The shared Notion page `performance-workshop` (Dead Shot's workspace) has a `jmeter` section, placed after "Workload profiles and test placement".
Every JMeter test added to this repository gets an entry there, in this format:

- **Test name**
  - **Description:** what the test does and why
  - **Command:** the exact command to run it
  - **Configuration:** the properties/values used (users, ramp, duration, target, etc.)

Notion edits follow rule 1: show the exact text and its position first, then edit only after confirmation.
