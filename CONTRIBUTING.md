# Changes and owner approval

All changes, including documentation, configuration and project rules, go through a feature branch and pull request to `main`. Do not commit or push directly to `main`.

## Contributor workflow

Start from an up-to-date main with a clean working tree, create a feature branch, make the change, and run the relevant checks in [AGENTS.md](AGENTS.md). Commit only source/docs/config; exclude `.state/`, secrets, certificates, logs and local overrides. Push the feature branch and open a PR against main.

Describe the resulting behavior and checks performed. Leave the PR for **@SupradeepDanturti** to review. Approval is dismissed when new commits change an approved PR, so request another review after making changes.

The human owner makes the final merge decision. Agents must not approve, enable auto-merge, merge, use an owner exception, or weaken protections without explicit human authorization for that particular action/PR. Using the owner's authenticated account is not authorization by itself.

## GitHub enforcement

Two active branch rulesets target `refs/heads/main`:

- **Main: pull requests only:** every update requires a pull request. No bypass actors, including the owner. Force pushes and branch deletion are blocked.
- **Main: owner approval and merge:** restricts updates to the repository administrator through pull requests, and requires one approving review with code-owner review and dismissal of stale approvals. The administrator can bypass this second ruleset **for pull requests only**.

The administrator role currently belongs only to **SupradeepDanturti**, the owner of this personal repository. Other contributors may propose changes, but only the owner completes merges. The owner's merge is the final approval decision. The all-files `.github/CODEOWNERS` entry names the owner as reviewer; GitHub uses that entry once it is merged into the base branch.

Ruleset JSON in [.github/rulesets](.github/rulesets) records the settings. These files do not configure GitHub automatically; the matching rulesets were separately applied through GitHub's API. Changes to the files require corresponding explicit owner-authorized settings changes.

## Your own pull requests

GitHub does not permit authors to submit an approving review on their own PRs. For your own work, open a PR, inspect its changes and checks, then use GitHub's owner override to merge it. This is an explicit owner decision rather than a self-review. The separate no-bypass PR rule still prevents direct pushes to main.

The same applies to agent-created PRs using your account: they are authored as you. Review them yourself and merge through GitHub, or explicitly authorize the agent to merge that specific PR. An agent must never assume this approval.

Do not grant additional administrator roles or bypass access without reviewing this policy. Admin credentials and repository-setting permissions can change enforcement; branch rules cannot distinguish the human owner from an agent using the same credentials.

GitHub references: [creating rulesets and PR-only bypass](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository), [authors cannot approve their own PRs](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews), and [code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
