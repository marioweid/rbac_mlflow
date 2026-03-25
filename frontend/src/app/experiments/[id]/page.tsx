import Link from "next/link";

import { auth } from "@/auth";
import { apiFetch } from "@/lib/api";
import { formatDuration, formatTimestamp, statusColor } from "@/lib/format";
import type { DatasetSummary, ExperimentDetail, RunListResponse } from "@/lib/types";

import { RunEvaluationButton } from "./RunEvaluationButton";

function hasWriteAccess(groups: string[] | undefined, teamName: string): boolean {
  return (groups ?? []).some(
    (g) => g === `/${teamName}/engineers` || g === `/${teamName}/owners`,
  );
}

async function getExperiment(id: string): Promise<ExperimentDetail | null> {
  const res = await apiFetch(`/experiments/${id}`);
  if (!res.ok) return null;
  return (await res.json()) as ExperimentDetail;
}

async function getRuns(
  id: string,
  orderBy: string,
): Promise<RunListResponse | null> {
  const res = await apiFetch(
    `/experiments/${id}/runs?order_by=${encodeURIComponent(orderBy)}`,
  );
  if (!res.ok) return null;
  return (await res.json()) as RunListResponse;
}

async function getDatasets(id: string): Promise<DatasetSummary[]> {
  const res = await apiFetch(`/experiments/${id}/datasets`);
  if (!res.ok) return [];
  return (await res.json()) as DatasetSummary[];
}

export default async function ExperimentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ order_by?: string }>;
}) {
  const { id } = await params;
  const { order_by: orderBy } = await searchParams;
  const currentOrder = orderBy ?? "start_time DESC";

  const [experiment, runsData, datasets, session] = await Promise.all([
    getExperiment(id),
    getRuns(id, currentOrder),
    getDatasets(id),
    auth(),
  ]);

  if (experiment === null) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-600">Experiment not found or access denied.</p>
        <Link href="/dashboard" className="text-blue-600 underline mt-2 block">
          Back to dashboard
        </Link>
      </main>
    );
  }

  const runs = runsData?.runs ?? [];
  const canWrite = hasWriteAccess(session?.groups, experiment.team_name);

  return (
    <main className="max-w-6xl mx-auto p-6">
      <Link
        href="/dashboard"
        className="text-sm text-blue-600 hover:underline mb-4 block"
      >
        &larr; Back to dashboard
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold">{experiment.name}</h1>
        <div className="flex gap-3 mt-2 text-sm text-gray-600">
          <span className="bg-gray-100 rounded px-2 py-0.5">
            {experiment.team_name}
          </span>
          <span>{experiment.lifecycle_stage}</span>
          {experiment.creation_time !== null && (
            <span>Created {formatTimestamp(experiment.creation_time)}</span>
          )}
        </div>
      </div>

      {/* Datasets section */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">Datasets</h2>
          {canWrite && (
            <Link
              href={`/experiments/${id}/datasets/new`}
              className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700"
            >
              New dataset
            </Link>
          )}
        </div>

        {datasets.length === 0 ? (
          <p className="text-gray-500 text-sm">No datasets yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-600">
                  <th className="py-2 pr-6">Name</th>
                  <th className="py-2 pr-6">Rows</th>
                  <th className="py-2 pr-6">Updated</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((ds) => (
                  <tr
                    key={ds.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-2 pr-6">
                      <Link
                        href={`/experiments/${id}/datasets/${ds.id}`}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        {ds.name}
                      </Link>
                      <span className="block text-xs text-gray-400 font-mono truncate max-w-xs">
                        {ds.id}
                      </span>
                      {ds.description && (
                        <span className="block text-xs text-gray-500 truncate max-w-xs">
                          {ds.description}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-6">{ds.row_count}</td>
                    <td className="py-2 pr-6 text-gray-500">
                      {new Date(ds.updated_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Runs section */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-semibold">Runs</h2>
        {canWrite && (
          <RunEvaluationButton
            experimentId={id}
          />
        )}
      </div>

      {runs.length === 0 ? (
        <p className="text-gray-500">No runs found for this experiment.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-600">
                <th className="py-2 pr-4">Run Name</th>
                <th className="py-2 pr-4">
                  <SortLink
                    field="start_time"
                    label="Status"
                    currentOrder={currentOrder}
                    experimentId={id}
                  />
                </th>
                <th className="py-2 pr-4">Start Time</th>
                <th className="py-2 pr-4">Duration</th>
                <th className="py-2 pr-4">Metrics</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.run_id}
                  className="border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="py-2 pr-4">
                    <Link
                      href={`/experiments/${id}/runs/${run.run_id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {run.run_name ?? run.run_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className={`py-2 pr-4 ${statusColor(run.status)}`}>
                    {run.status}
                  </td>
                  <td className="py-2 pr-4 text-gray-500">
                    {formatTimestamp(run.start_time)}
                  </td>
                  <td className="py-2 pr-4 text-gray-500">
                    {formatDuration(run.start_time, run.end_time)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    {run.metrics
                      .slice(0, 3)
                      .map((m) => `${m.key}=${m.value.toFixed(3)}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function SortLink({
  field,
  label,
  currentOrder,
  experimentId,
}: {
  field: string;
  label: string;
  currentOrder: string;
  experimentId: string;
}) {
  const isAsc = currentOrder === `${field} ASC`;
  const nextOrder = isAsc ? `${field} DESC` : `${field} ASC`;
  return (
    <Link
      href={`/experiments/${experimentId}?order_by=${encodeURIComponent(nextOrder)}`}
      className="hover:underline"
    >
      {label} {currentOrder.startsWith(field) ? (isAsc ? "\u25B2" : "\u25BC") : ""}
    </Link>
  );
}
