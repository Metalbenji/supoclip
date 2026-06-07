import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { serializeSavedWorkflow, validateWorkflowName, validateWorkflowValues } from "../_shared";

async function getSessionUserId(): Promise<string | null> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });
  return session?.user?.id ?? null;
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ workflowId: string }> },
) {
  try {
    const userId = await getSessionUserId();
    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { workflowId } = await context.params;
    const body = (await request.json()) as Record<string, unknown>;
    const updateData: Record<string, unknown> = {};

    if ("name" in body) {
      const name = validateWorkflowName(body.name);
      if (!name) {
        return NextResponse.json({ error: "Workflow name is required and must be 1-120 characters" }, { status: 400 });
      }
      const existing = await ((prisma as any).savedWorkflow as any).findFirst({
        where: {
          user_id: userId,
          id: { not: workflowId },
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
      updateData.name = name;
    }

    const hasWorkflowValueFields =
      "reviewBeforeRenderEnabled" in body ||
      "timelineEditorEnabled" in body ||
      "transitionsEnabled" in body ||
      "transcriptionProvider" in body ||
      "whisperModelSize" in body ||
      "defaultFramingMode" in body ||
      "faceDetectionMode" in body ||
      "fallbackCropPosition" in body ||
      "faceAnchorProfile" in body;

    if (hasWorkflowValueFields) {
      const workflowValues = validateWorkflowValues(body);
      if (!workflowValues) {
        return NextResponse.json({ error: "Invalid workflow values" }, { status: 400 });
      }
      Object.assign(updateData, workflowValues);
    }

    if (Object.keys(updateData).length === 0) {
      return NextResponse.json({ error: "No workflow changes provided" }, { status: 400 });
    }

    const existingWorkflow = await ((prisma as any).savedWorkflow as any).findFirst({
      where: {
        id: workflowId,
        user_id: userId,
      },
      select: { id: true },
    });
    if (!existingWorkflow) {
      return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
    }

    const updated = await ((prisma as any).savedWorkflow as any).update({
      where: { id: workflowId },
      data: updateData,
    });

    return NextResponse.json({ workflow: serializeSavedWorkflow(updated) });
  } catch (error) {
    console.error("Failed to update saved workflow:", error);
    return NextResponse.json({ error: "Failed to update workflow" }, { status: 500 });
  }
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ workflowId: string }> },
) {
  try {
    const userId = await getSessionUserId();
    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { workflowId } = await context.params;
    const existingWorkflow = await ((prisma as any).savedWorkflow as any).findFirst({
      where: {
        id: workflowId,
        user_id: userId,
      },
      select: { id: true },
    });
    if (!existingWorkflow) {
      return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
    }

    await prisma.$transaction(async (tx) => {
      await (tx.user as any).updateMany({
        where: {
          id: userId,
          default_saved_workflow_id: workflowId,
        },
        data: {
          default_saved_workflow_id: null,
          default_workflow_source: "custom",
          default_processing_profile: "custom",
        },
      });
      await ((tx as any).savedWorkflow as any).delete({
        where: { id: workflowId },
      });
    });

    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Failed to delete saved workflow:", error);
    return NextResponse.json({ error: "Failed to delete workflow" }, { status: 500 });
  }
}
