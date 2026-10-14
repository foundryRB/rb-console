---
title: Visual identity
id: DOC-BRAND-001
type: Reference
status: Active
updated: "2026-09-13"
summary: The Vodafone Portugal Digital identity in the fleet and delivery cockpit.
---

Foundry Console is a dark cockpit on the Vodafone Portugal Digital stage: a near-black ground, the lockup as the one mark in the masthead, the brand's red as the accent. Fleet tables and delivery controls retain their wide operational layout.

## Source ownership

| Surface | Source |
| --- | --- |
| Palette, typography, ambient motion and spacing | `frontend/src/index.css`, `frontend/tailwind.config.js` |
| Lockup (the one mark in the masthead) | `frontend/src/components/Lockup.tsx` |
| Application frame | `frontend/src/views/templates/Cockpit.tsx` |
| The living stage (drifting glows, red grids, rising motes) | the `vfpt stage` block at the end of `frontend/src/index.css` |
| Browser mark | `frontend/public/favicon.svg` |

Charcoal panels and the brand face sit above the stage, the app's one ambient layer. Motion is transform and opacity only, stops for reduced motion and disappears in print. Status colours retain their operational meanings. Panels are tinted glass at a 68% fill with no backdrop blur: a blur would smear the stage's drift and erase its motes. Inputs are solid.

Customer previews retain their own identity inside the preview frame. Delivery data, commands and exported records retain their domain formats.
