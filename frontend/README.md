# Foundry Console frontend

The watch-and-drive SPA for the Foundry Console orchestrator. A dark cockpit over
the foundry floor: watch deliveries move down the five-phase line, and drive the
next launch. React + TypeScript + Vite + Tailwind, talking to the orchestrator's
REST `/api`.

## Layout

MVVM (Model / ViewModel / View), per the house frontend conventions:

- `src/models/` M: types mechanically generated from the committed offline OpenAPI seed.
- `src/viewmodels/<feature>/` VM: SAM (state / actions / model) over Zustand.
  HTTP fetch lives in actions; lifecycle and command availability come from the API.
- `src/views/` V: Atomic Design (atoms, molecules, organisms, pages, templates).
- `src/components/ui/` framework-level primitives (button, card, badge, input).

## Screens

- `/` Deliveries: watch a list of delivery cards (five-phase strip, gates, next
  command) plus a Start delivery form.
- `/d?repo=<path>` Delivery detail: one delivery's full state, its gates and
  records, and a Plan next button.

## Develop

```bash
npm ci
npm run dev      # http://localhost:5173, proxies /api to http://127.0.0.1:8000
```

Run the orchestrator's REST door on `127.0.0.1:8000` alongside it.

```bash
npm run models:sync # export backend contract and generate types after API changes
npm run build    # offline model generation, type-check, production build
npm run lint      # eslint
npm test          # vitest + Testing Library component tests (src/**/*.test.tsx, jsdom)
npm run e2e       # Playwright responsive regression suite (stubs /api; Python projects fixtures through backend pure rules)
```

## Responsive layout

The cockpit is a dense desktop instrument panel, and staying that way on a wide screen
is a hard requirement. The rule that keeps mobile and tablet work from eroding it:

**Desktop is the `lg` breakpoint (1024px) and up. Every desktop rule lives behind an
`lg:` prefix; mobile and tablet-portrait changes live only in the base / `sm:` / `md:` /
`max-lg:` layers.** Because Tailwind is mobile-first, an `lg:` rule always wins at
`>= 1024px`, so touching the smaller layers cannot move the desktop layout. When a desktop
value must differ from mobile, move that value to `lg:` and put the mobile variant in the
base - never the other way round.

The two shapes this produces:

- **Masthead** (`views/templates/Cockpit.tsx`): the page controls (`bar`) render inline at
  `lg`; below it they collapse behind a "Controls" disclosure so the bar never wraps into a
  wall.
- **Two-pane cockpits** (delivery, live-project, maintenance): a side-by-side grid at `lg`;
  below it the panes are one column and a `views/atoms/PaneToggle.tsx` tab bar (`lg:hidden`)
  picks which one shows. Tablet portrait (768-1023px) gets this single-column tabbed layout,
  not a width-starved split; tablet landscape (>= 1024px) gets the full desktop cockpit.

`e2e/responsive.spec.ts` locks all of this: it asserts the desktop layout is unchanged and
the mobile/tablet layer has no horizontal overflow at 390 / 834 / 1280px. Run it (or trust
CI's `frontend-e2e` job) after any layout change.

The production client is an independent nginx web image. It serves static assets and
proxies same-origin `/api` to the loopback backend. The API does not serve the client.
Phase content and file trees load on explicit selection; metadata-only page opening
does not fetch repository blobs. Unknown command outcomes retain their operation ID
and offer persisted receipt inspection when the API supplies a receipt key.
