import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { config as loadEnv } from "dotenv";
import { defineConfig } from "prisma/config";

for (const envFile of ["../.env", ".env", ".env.local"]) {
  const envPath = resolve(process.cwd(), envFile);
  if (existsSync(envPath)) {
    loadEnv({ path: envPath, override: true, quiet: true });
  }
}

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    url: process.env["DATABASE_URL"],
  },
});
