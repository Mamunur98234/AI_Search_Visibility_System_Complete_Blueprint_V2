import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // Untrusted content must never be injected as HTML.
      "react/no-danger": "error",
      "jsx-a11y/no-autofocus": "off",
    },
  },
  { ignores: [".next/**", ".next-e2e/**", "node_modules/**", "src/lib/api-types.ts", "playwright-report/**", "test-results/**"] },
];

export default config;
