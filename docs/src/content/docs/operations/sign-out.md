---
title: Sign out of the console
id: DOC-FC-OPS-SIGN-OUT
type: Guide
status: Active
updated: "2026-10-08"
summary: End the browser's console session, including on a phone where the console runs as an installed app.
---

Sign out ends the console session the sign-in proxy holds for this browser. On a phone, where the
console runs full-screen from the Home Screen with no address bar, it is the way the session ends.

## When to use

You are done on a shared device, or you want to sign in as someone else.

## Steps

1. Open Settings and find the Session card. It appears only where the sign-in proxy fronts the
   install.
2. Press Sign out. The browser leaves the console for the proxy's own `/oauth2/sign_out`.
3. To end the identity provider's session as well, sign out of the provider too: the proxy's
   sign-out clears the proxy's cookie only.

## Verify

- The next visit asks the identity provider again; while the provider still holds its own session,
  it signs you straight back in.

## Read next

- [Deploy an install](../deploy/)
- [The admission module](../../modules/admission/)
