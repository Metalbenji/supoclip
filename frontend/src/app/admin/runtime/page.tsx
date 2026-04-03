"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/lib/auth-client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import Link from "next/link";
import { ArrowLeft, AlertCircle } from "lucide-react";

interface RuntimeOverview {
  workers: Array<Record<string, unknown>>;
  queues: Array<{ queue_name: string; depth: number }>;
  local_whisper_runtime?: Record<string, unknown>;
  local_whisper_models?: Array<Record<string, unknown>>;
  recent_failures?: Array<Record<string, unknown>>;
  failure_summary?: Array<Record<string, unknown>>;
  retention_policy?: Record<string, unknown>;
}

export default function RuntimeAdminPage() {
  const { data: session, isPending } = useSession();
  const [overview, setOverview] = useState<RuntimeOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCleaning, setIsCleaning] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    const load = async () => {
      if (!session?.user?.id) return;
      try {
        setIsLoading(true);
        const response = await fetch(`${apiUrl}/tasks/runtime-overview`, {
          headers: {
            user_id: session.user.id,
          },
        });
        if (!response.ok) {
          throw new Error(`Failed to load runtime overview: ${response.status}`);
        }
        setOverview(await response.json());
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load runtime overview");
      } finally {
        setIsLoading(false);
      }
    };
    void load();
  }, [apiUrl, session?.user?.id]);

  const handleCleanup = async () => {
    if (!session?.user?.id) return;
    try {
      setIsCleaning(true);
      const response = await fetch(`${apiUrl}/tasks/admin/cleanup-artifacts`, {
        method: "POST",
        headers: {
          user_id: session.user.id,
        },
      });
      if (!response.ok) {
        throw new Error(`Cleanup failed: ${response.status}`);
      }
      const refreshed = await fetch(`${apiUrl}/tasks/runtime-overview`, {
        headers: {
          user_id: session.user.id,
        },
      });
      if (refreshed.ok) {
        setOverview(await refreshed.json());
      }
      setError(null);
    } catch (cleanupError) {
      setError(cleanupError instanceof Error ? cleanupError.message : "Cleanup failed");
    } finally {
      setIsCleaning(false);
    }
  };

  if (isPending || isLoading) {
    return <div className="min-h-screen bg-white p-6 text-sm text-gray-600">Loading runtime overview...</div>;
  }

  if (!session?.user) {
    return <div className="min-h-screen bg-white p-6 text-sm text-gray-600">Sign in to view runtime diagnostics.</div>;
  }

  return (
    <div className="min-h-screen bg-white">
      <div className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-6">
          <Link href="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-black">Runtime Overview</h1>
            <p className="text-sm text-gray-600">Workers, queues, model cache status, failures, and retention policy.</p>
          </div>
          <Button variant="outline" onClick={() => void handleCleanup()} disabled={isCleaning}>
            {isCleaning ? "Cleaning..." : "Run Cleanup"}
          </Button>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
        {error ? (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {(overview?.queues || []).map((queue) => (
            <Card key={queue.queue_name}>
              <CardContent className="p-4">
                <p className="text-xs text-gray-500">Queue</p>
                <p className="font-medium text-black">{queue.queue_name}</p>
                <p className="mt-2 text-sm text-gray-600">Depth {queue.depth}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-sm font-semibold text-black">Workers</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {(overview?.workers || []).map((worker, index) => (
                <div key={`${worker.key || worker.queue_name || index}`} className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-black">{String(worker.queue_name || worker.worker_name || "worker")}</p>
                    <Badge className="bg-emerald-100 text-emerald-800">Healthy</Badge>
                  </div>
                  <p className="mt-1 text-xs text-gray-600">{String(worker.timestamp || "")}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-sm font-semibold text-black">Whisper Runtime</h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-sm">
              <div>
                <p className="text-xs text-gray-500">CUDA</p>
                <p className="font-medium">{String(overview?.local_whisper_runtime?.cuda_available ?? "n/a")}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">GPU</p>
                <p className="font-medium">{String(overview?.local_whisper_runtime?.gpu_device_name ?? "n/a")}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Triton kernels</p>
                <p className="font-medium">{String(overview?.local_whisper_runtime?.triton_timing_kernels_enabled ?? "n/a")}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Fallback</p>
                <p className="font-medium">{String(overview?.local_whisper_runtime?.triton_fallback_reason ?? "none")}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {(overview?.local_whisper_models || []).map((model) => (
                <Badge key={String(model.value)} variant="outline" className="bg-white">
                  {String(model.label)}: {String(model.cache_status)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="text-sm font-semibold text-black">Failure Summary</h2>
              {(overview?.failure_summary || []).map((entry, index) => (
                <div key={`${entry.failure_code || index}`} className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm">
                  <p className="font-medium text-black">{String(entry.failure_code || "system")}</p>
                  <p className="text-gray-600">Count {String(entry.count || 0)}</p>
                  <p className="text-xs text-gray-500">{String(entry.representative_message || "")}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="text-sm font-semibold text-black">Retention Policy</h2>
              {Object.entries(overview?.retention_policy || {}).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">{key}</span>
                  <span className="font-medium text-black">{String(value)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
