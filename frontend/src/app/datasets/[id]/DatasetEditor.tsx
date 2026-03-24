"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useSession } from "next-auth/react";

import { clientApiFetch } from "@/lib/client-api";
import type { DatasetDetail, DatasetVersionInfo } from "@/lib/types";

interface Props {
  dataset: DatasetDetail;
  canWrite: boolean;
}

export function DatasetEditor({ dataset, canWrite }: Props) {
  const router = useRouter();
  const { data: session } = useSession();

  const initialVersion = dataset.versions.at(-1)?.version ?? 1;
  const [rows, setRows] = useState<string>(
    JSON.stringify(dataset.rows, null, 2),
  );
  const [selectedVersion, setSelectedVersion] =
    useState<number>(initialVersion);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadVersion(v: DatasetVersionInfo) {
    setSelectedVersion(v.version);
    const res = await clientApiFetch(
      `/datasets/${dataset.id}/versions/${v.version}`,
      session?.accessToken,
    );
    if (res.ok) {
      const data = (await res.json()) as unknown;
      setRows(JSON.stringify(data, null, 2));
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const parsed = JSON.parse(rows) as unknown;
      if (!Array.isArray(parsed)) {
        setError("Rows must be a JSON array.");
        return;
      }
      const res = await clientApiFetch(
        `/datasets/${dataset.id}`,
        session?.accessToken,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows: parsed }),
        },
      );
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        setError(body.detail ?? `Error ${res.status}`);
        return;
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof SyntaxError ? "Invalid JSON." : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex gap-6">
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-lg font-semibold">
            Rows{" "}
            <span className="text-sm font-normal text-gray-500">
              (v{selectedVersion})
            </span>
          </h2>
          {canWrite && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving\u2026" : "Save as new version"}
            </button>
          )}
        </div>

        {error !== null && <p className="text-red-600 text-sm mb-2">{error}</p>}

        <textarea
          value={rows}
          onChange={(e) => setRows(e.target.value)}
          readOnly={!canWrite}
          className="w-full h-[60vh] font-mono text-sm border border-gray-200 rounded p-3 resize-y focus:outline-none focus:border-blue-400"
          spellCheck={false}
        />
      </div>

      <div className="w-48 shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Version history
        </h3>
        <ul className="space-y-1">
          {[...dataset.versions].reverse().map((v) => (
            <li key={v.version}>
              <button
                onClick={() => loadVersion(v)}
                className={`w-full text-left text-sm px-2 py-1.5 rounded ${
                  v.version === selectedVersion
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "hover:bg-gray-100 text-gray-700"
                }`}
              >
                <span className="font-mono">v{v.version}</span>
                <span className="text-xs text-gray-500 block">
                  {v.row_count} rows
                </span>
                <span className="text-xs text-gray-400 block">
                  {new Date(v.created_at).toLocaleDateString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
