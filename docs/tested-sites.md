# Tested Sites Evidence

This document records representative sites that were used as manual validation evidence during development. It is not an exhaustive benchmark suite.

| URL | Category | Expected Auth Pattern | Observed Result | Primary Component | Snippet Quality |
| --- | --- | --- | --- | --- | --- |
| `https://github.com/login` | Developer SaaS | Traditional login + secondary auth options | `found` | `traditional` | Focused login form |
| `https://substack.com/sign-in` | Publishing / Blog | Email-first / multi-step | `partial_auth_surface` | `multi_step` | Focused auth shell |
| `https://account.box.com/login` | SaaS | Dynamic login shell | `found` or `partial_auth_surface` | `multi_step` | Acceptable with browser rendering |
| `https://www.reddit.com/login/` | Community / Social | Traditional + provider auth | `found` | `traditional` | Focused form |
| `https://apply.coveredca.com/static/lw-web/login` | Service Portal | Wrapper-heavy traditional login | `found` | `traditional` | Focused form within wrapper |

## Notes

- These sites were chosen to cover multiple auth patterns rather than only simple forms.
- Harder pages may rely on rendered DOM state, which is why Playwright is part of the main analysis path.
- Challenge or blocked pages are reported as `blocked_or_inconclusive`, with `protected_page` set when the final message indicates a blocked or challenged response.

## Example Output Patterns

### Traditional Login

- top-level status: `found`
- primary component: `traditional`
- snippet: `<form>...</form>`

### Email-First Flow

- top-level status: `partial_auth_surface`
- primary component: `multi_step`
- snippet: auth shell containing identity input and continue action
- optional extra evidence: `partial_html_markup`

### Mixed Auth Page

- top-level status: `found`
- components may include `traditional`, `oauth`, or `passwordless` entries when those surfaces are genuinely visible in the same page state
