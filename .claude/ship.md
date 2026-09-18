gate: cd server && uv run pytest -q && cd ../packages/lumiface && flutter analyze && flutter test && cd ../.. && bun run typecheck && bun run test:react && bun run check:docs
ports: 8000, 8080, 3002, 3010
