import Link from "next/link";

import { auth } from "@/auth";
import { apiFetch } from "@/lib/api";
import type { DatasetSummary } from "@/lib/types";

async function getDatasets(): Promise<DatasetSummary[]> {
  const res = await apiFetch("/datasets");
  if (!res.ok) return [];
  return (await res.json()) as DatasetSummary[];
}

function hasWriteAccess(groups: string[] | undefined): boolean {
  return (groups ?? []).some(
    (g) => g.endsWith("/engineers") || g.endsWith("/owners"),
  );
}

export default async function DatasetsPage() {
  const [datasets, session] = await Promise.all([getDatasets(), auth()]);
  const canWrite = hasWriteAccess(session?.groups);

  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Datasets</h1>
        {canWrite && (
          <Link
            href="/datasets/new"
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
          >
            New dataset
          </Link>
        )}
      </div>

      {datasets.length === 0 ? (
        <p className="text-gray-500">
          No datasets found. You may not be a member of any team, or no
          datasets have been created yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-600">
                <th className="py-2 pr-6">Name</th>
                <th className="py-2 pr-6">Team</th>
                <th className="py-2 pr-6">Version</th>
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
                      href={`/datasets/${ds.id}`}
                      className="text-blue-600 hover:underline font-medium"
                    >
                      {ds.name}
                    </Link>
                    {ds.description && (
                      <span className="block text-xs text-gray-400 truncate max-w-xs">
                        {ds.description}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-6">
                    <span className="inline-block text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5">
                      {ds.team_name}
                    </span>
                  </td>
                  <td className="py-2 pr-6 font-mono">v{ds.latest_version}</td>
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
    </main>
  );
}
