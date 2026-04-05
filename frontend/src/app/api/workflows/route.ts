import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { serializeSavedWorkflow, validateWorkflowName, validateWorkflowValues } from "./_shared";

async function getSessionUserId(): Promise<string | null> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });
  return session?.user?.id ?? null;
}

export async function GET() {
  try {
    const userId = await getSessionUserId();
    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const workflows = await ((prisma as any).savedWorkflow as any).findMany({
      where: { user_id: userId },
      orderBy: [{ updated_at: "desc" }, { created_at: "desc" }],
    });

    return NextResponse.json({
      workflows: workflows.map(serializeSavedWorkflow),
    });
  } catch (error) {
    console.error("Failed to list saved workflows:", error);
    return NextResponse.json({ error: "Failed to load workflows" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const userId = await getSessionUserId();
    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = (await request.json()) as Record<string, unknown>;
    const name = validateWorkflowName(body.name);
    if (!name) {
      return NextResponse.json({ error: "Workflow name is required and must be 1-120 characters" }, { status: 400 });
    }
    const workflowValues = validateWorkflowValues(body);
    if (!workflowValues) {
      return NextResponse.json({ error: "Invalid workflow values" }, { status: 400 });
    }

    const existing = await ((prisma as any).savedWorkflow as any).findFirst({
      where: {
        user_id: userId,
        name: {
          equals: name,
          mode: "insensitive",
        },
      },
      select: { id: true },
    });
    if (existing) {
      return NextResponse.json({ error: "A workflow with that name already exists" }, { status: 409 });
    }

    const created = await ((prisma as any).savedWorkflow as any).create({
      data: {
        user_id: userId,
        name,
        ...workflowValues,
      },
    });

    return NextResponse.json({ workflow: serializeSavedWorkflow(created) }, { status: 201 });
  } catch (error) {
    console.error("Failed to create saved workflow:", error);
    return NextResponse.json({ error: "Failed to create workflow" }, { status: 500 });
  }
}
