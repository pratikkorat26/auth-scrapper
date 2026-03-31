# AI Engineer Technical Assessment Summary

## Objective

Build a small application that can inspect website markup, identify authentication components, and return the relevant HTML snippet for review.

## What Was Built

This submission is a full-stack auth detection app with:

- a React UI that accepts any public URL
- a FastAPI backend that analyzes the page
- deterministic auth detection for login forms, OAuth buttons, email-first flows, and passwordless entry points
- HTML snippet output for the strongest visible auth surface

## Approach

The system uses Playwright-first rendering so dynamic auth pages can be analyzed after the page is fully rendered. A rule-based detector then evaluates the rendered HTML and selects the best visible auth component. Gemini is optional and used only as an audit step for ambiguous cases.

This design was chosen to keep the core result deterministic, explainable, and robust on modern JavaScript-heavy websites.

## Why This Is Reliable

- Works on static and dynamic pages
- Returns structured results, not just raw text
- Prefers the smallest meaningful auth snippet over large page wrappers
- Preserves multiple auth methods when they are genuinely visible on the same page
- Includes automated backend tests for traditional, OAuth, email-first, passwordless, and wrapper-heavy pages

## What Reviewers Should Check

1. Start the backend and frontend locally.
2. Submit a public login URL.
3. Confirm the app returns:
   - a status
   - a focused auth HTML snippet
   - a components list with detected auth types

Recommended demo URL:

- `https://github.com/login`

## Sample Result

Typical outputs include:

- `traditional` for standard username/password forms
- `multi_step` for email-first flows
- `oauth` for provider-only sign-in clusters
- `passwordless` for passkey, magic link, or OTP-first entry points

## Limitations

- Some sites may show anti-bot or challenge pages instead of login UI.
- Some login flows vary by region, session state, or A/B experiment.
- The app inspects markup only and never submits credentials.

## Conclusion

The project satisfies the requested assessment behaviors while keeping the main detection path deterministic and reviewer-friendly.
