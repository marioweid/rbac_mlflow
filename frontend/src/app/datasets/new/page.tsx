"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useSession } from "next-auth/react";

import { clientApiFetch } from "@/lib/client-api";
import type { DatasetResponse } from "@/lib/types";

function writeTeamsFromGroups(groups: string[]): string[] {
  return groups
    .filter((g) => g.endsWith("/engineers") || g.endsWith("/owners"))
    .map((g) => {
      const parts = g.split("/");
      return parts.at(-2) ?? "";
    })
    .filter(Boolean);
}

export default function NewDatasetPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const writeTeams = writeTeamsFromGroups(session?.groups ?? []);

  const [name, setName] = useState("");
  const [teamName, setTeamName] = useState(writeTeams[0] ?? "");
  const [description, setDescription] = useState("");
  const [rowsJson, setRowsJson] = useState("[]");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const rows = JSON.parse(rowsJson) as unknown;
      if (!Array.isArray(rows)) {
        setError("Rows must be a JSON array.");
        return;
      }
      const res = await clientApiFetch("/datasets", session?.accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, team_name: teamName, description, rows }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        setError(body.detail ?? `Error ${res.status}`);
        return;
      }
      const created = (await res.json()) as DatasetResponse;
      router.push(`/datasets/${created.id}`);
    } catch (e) {
      setError(e instanceof SyntaxError ? "Invalid JSON in rows." : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="max-w-2xl mx-auto p-6">
      <Link
        href="/datasets"
        className="text-sm text-blue-600 hover:underline mb-4 block"
      >
        &larr; Back to datasets
      </Link>

      <h1 className="text-2xl font-bold mb-6">New dataset</h1>

      {writeTeams.length === 0 ? (
        <p className="text-gray-500">
          You need engineer or owner access to a team to create datasets.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Team</label>
            <select
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              required
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            >
              {writeTeams.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              Description{" "}
              <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              Rows{" "}
              <span className="text-gray-400 font-normal">(JSON array)</span>
            </label>
            <textarea
              value={rowsJson}
              onChange={(e) => setRowsJson(e.target.value)}
              rows={10}
              spellCheck={false}
              className="w-full font-mono text-sm border border-gray-200 rounded px-3 py-2 focus:outline-none focus:border-blue-400 resize-y"
            />
          </div>

          {error !== null && <p className="text-red-600 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Creating\u2026" : "Create dataset"}
          </button>
        </form>
      )}
    </main>
  );
}
