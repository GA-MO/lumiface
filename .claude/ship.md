gate: cd server && uv run pytest -q && cd ../packages/facegate && flutter analyze && flutter test && cd ../.. && bun run typecheck && bun run test:react
ports: 8000, 8080, 3002, 3010
