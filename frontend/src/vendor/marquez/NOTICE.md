# Marquez graph reuse

These files are from Marquez 0.50.0, commit `4984ca939b3a6f59e1092c6397702eb1e53ff1cc`, under Apache-2.0:

- `layout/useLayout.ts` — graph layout, positioning, and edge routing
- `utils/hooks.ts` — stable callback hook
- `types.ts` — graph types

Upstream: https://github.com/MarquezProject/marquez/tree/0.50.0/web/libs/graph/src

Copyright contributors to the Marquez project. Full license is retained in `LICENSE`.

Local changes: explicit initial values for React 19 refs; use ELK's bundled browser entry and permit its inline fallback when a Worker URL is not provided; preserve valid zero-valued coordinates; select GREEDY cycle breaking and NETWORK_SIMPLEX layering so acyclic data flows progress left to right instead of the upstream compact two-layer arrangement. Increase layer and node spacing to give curved connectors room. Integration UI, controls, and accessible node cards are project code. The full Marquez web application is not embedded or claimed as our own.
