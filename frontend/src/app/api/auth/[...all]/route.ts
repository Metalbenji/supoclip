import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const { GET, POST, PATCH, PUT, DELETE } = toNextJsHandler(auth.handler);
