import Link from "next/link";

import { auth } from "@/auth";
import { apiFetch } from "@/lib/api";
import type { DatasetDetail } from "@/lib/types";

import { DatasetEditor } from "./DatasetEditor";

async function getDataset(
  experimentId: string,
  datasetId: string,
): Promise<DatasetDetail | null> {
  const res = await apiFetch(
    `/experiments/${experimentId}/datasets/${datasetId}`,
  );
  if (!res.ok) return null;
  return (await res.json()) as DatasetDetail;
}

function hasWriteAccess(groups: string[] | undefined): boolean {
  return (groups ?? []).some(
    (g) => g.endsWith("/engineers") || g.endsWith("/owners"),
  );
}

export default async function DatasetPage({
  params,
}: {
  params: Promise<{ id: string; datasetId: string }>;
}) {
  const { id: experimentId, datasetId } = await params;
  const [dataset, session] = await Promise.all([
    getDataset(experimentId, datasetId),
    auth(),
  ]);

  if (dataset === null) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-600">Dataset not found or access denied.</p>
        <Link
          href={`/experiments/${experimentId}`}
          className="text-blue-600 underline mt-2 block"
        >
          Back to experiment
        </Link>
      </main>
    );
  }

  const canWrite = hasWriteAccess(session?.groups);

  return (
    <main className="max-w-6xl mx-auto p-6">
      <Link
        href={`/experiments/${experimentId}`}
        className="text-sm text-blue-600 hover:underline mb-4 block"
      >
        &larr; Back to experiment
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold">{dataset.name}</h1>
        <div className="flex gap-3 mt-2 text-sm text-gray-600">
          <span className="font-mono text-gray-400 text-xs">{dataset.id}</span>
          {dataset.description && <span>{dataset.description}</span>}
        </div>
      </div>

      <DatasetEditor
        dataset={dataset}
        experimentId={experimentId}
        canWrite={canWrite}
      />
    </main>
  );
}
