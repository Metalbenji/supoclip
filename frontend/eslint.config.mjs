import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...nextVitals,
  {
    ignores: ["src/generated/prisma/**"],
  },
];

export default eslintConfig;
