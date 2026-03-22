import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { formatDuration, formatTimestamp, statusColor } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

async function getRunDetail(
  experimentId: string,
  runId: string,
): Promise<RunDetail | null> {
  const res = await apiFetch(`/experiments/${experimentId}/runs/${runId}`);
  if (!res.ok) return null;
  return (await res.json()) as RunDetail;
}

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id: experimentId, runId } = await params;
  const run = await getRunDetail(experimentId, runId);

  if (run === null) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-600">Run not found or access denied.</p>
        <Link
          href={`/experiments/${experimentId}`}
          className="text-blue-600 underline mt-2 block"
        >
          Back to experiment
        </Link>
      </main>
    );
  }

  const judgeMetrics = run.metrics.filter((m) => m.key.startsWith("judge_"));
  const regularMetrics = run.metrics.filter(
    (m) => !m.key.startsWith("judge_"),
  );
  const visibleTags = run.tags.filter((t) => !t.key.startsWith("mlflow."));

  return (
    <main className="max-w-6xl mx-auto p-6">
      <Link
        href={`/experiments/${experimentId}`}
        className="text-sm text-blue-600 hover:underline mb-4 block"
      >
        &larr; Back to experiment
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold">
          {run.run_name ?? run.run_id.slice(0, 8)}
        </h1>
        <div className="flex gap-3 mt-2 text-sm text-gray-600">
          <span className={statusColor(run.status)}>{run.status}</span>
          <span>Started {formatTimestamp(run.start_time)}</span>
          <span>Duration {formatDuration(run.start_time, run.end_time)}</span>
        </div>
        {run.artifact_uri !== null && (
          <p className="text-xs text-gray-400 mt-1 font-mono">
            Artifacts: {run.artifact_uri}
          </p>
        )}
      </div>

      <Section title="Metrics">
        {regularMetrics.length === 0 ? (
          <p className="text-gray-500 text-sm">No metrics recorded.</p>
        ) : (
          <KVTable
            rows={regularMetrics.map((m) => ({
              key: m.key,
              value: m.value.toFixed(4),
            }))}
          />
        )}
      </Section>

      {judgeMetrics.length > 0 && (
        <Section title="Judge Scores">
          <KVTable
            rows={judgeMetrics.map((m) => ({
              key: m.key,
              value: m.value.toFixed(4),
            }))}
          />
        </Section>
      )}

      <Section title="Parameters">
        {run.params.length === 0 ? (
          <p className="text-gray-500 text-sm">No parameters recorded.</p>
        ) : (
          <KVTable rows={run.params} />
        )}
      </Section>

      {visibleTags.length > 0 && (
        <Section title="Tags">
          <KVTable rows={visibleTags} />
        </Section>
      )}
    </main>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold mb-2">{title}</h2>
      {children}
    </div>
  );
}

function KVTable({ rows }: { rows: { key: string; value: string }[] }) {
  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b border-gray-200 text-left text-gray-600">
          <th className="py-1.5 pr-4">Key</th>
          <th className="py-1.5">Value</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-gray-100">
            <td className="py-1.5 pr-4 font-mono text-gray-700">{row.key}</td>
            <td className="py-1.5 font-mono">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
