# FarmOps operator design system

## Product read

Trust-first, mobile-first farm operations command center for field managers
and engineers. The interface uses a bright agritech control-room language and
puts evidence, uncertainty, and safe action ahead of decoration.

Design variance is 4/10, motion intensity is 3/10, and visual density is 7/10.
This is a greenfield product UI, not a marketing page.

## Foundations

- One semantic token system implemented with CSS custom properties and
  Tailwind 4 utilities. Tokens cover backgrounds, raised surfaces, borders,
  text, success, warning, critical, information, freshness and autonomy.
- Light is the default, high-contrast operational theme for outdoor use.
  Forest green marks healthy farm state, blue marks plan/information actions,
  amber marks proposals and warning, and red is reserved for real failures.
- System UI typography uses Segoe UI Variable when available. Numbers and IDs
  use the platform monospace stack.
- Radius scale: 10px controls, 14px panels, circular icon controls only.
- Surfaces are separated by spacing and one-pixel borders. Shadows are limited
  to dialogs and the sticky shell.

## Command-center composition

- Desktop uses a compact left rail, a utility header and a three-part decision
  row: live farm map, immediate attention and active plan.
- The next row separates evidence health, DCS/autonomy, the top field task,
  and the real Agent trace. Assumptions and the two verification layers remain
  visible without navigating away.
- The spatial farm is a CSS/DOM progressive enhancement driven exclusively by
  FarmWorldViewModel. It has no API, MQTT, policy or approval logic. When it
  is unavailable, a semantic DOM list preserves the same operational facts.
- At mobile widths the layout recomposes to attention, farm, plan, tasks,
  trust, Agent activity and verification. The fixed bottom navigation has
  touch-sized targets; no operational task requires canvas interaction.

## Interaction rules

- Every async surface has loading, error, empty, and success states.
- Status is always written as text and paired with an icon. Color never carries
  meaning alone.
- Action and outcome verification remain separate in every layout.
- Destructive or operational actions require a visible operator token state and
  keep the exact revision hash in view.
- Automatic refresh runs every five seconds, preserves the last good payload,
  and announces errors without blanking the console.
- Motion is limited to hover, focus, dialog, and state feedback. Reduced-motion
  preferences disable nonessential transitions.

## Responsive contract

- Primary acceptance viewport: 390 by 844 pixels.
- Below 768px, all multi-column content becomes one column and navigation moves
  to a fixed bottom bar with 44px minimum targets.
- IDs, predicates, hashes, and evidence references wrap anywhere and never
  force horizontal scrolling.
- Data tables are avoided. Structured records use definition lists and grouped
  panels that remain readable on a phone.

## Accessibility contract

- Semantic landmarks, a skip link, visible focus, native controls, live regions,
  and labelled dialogs are mandatory.
- Body text and controls target WCAG AA contrast in both themes.
- Loading indicators expose `aria-busy`; critical notifications use an alert
  role; background polling uses polite announcements only on meaningful errors.
