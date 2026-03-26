"use client";

import { useState } from "react";

export interface RetrievedContextEntry {
  doc_uri: string;
  content: string;
}

export interface ExtraInput {
  key: string;
  value: string;
}

export interface DatasetRow {
  // inputs
  question: string;
  extraInputs: ExtraInput[];
  // expectations
  expectedResponse: string;
  expectedFacts: string[];
  expectedRetrievedContext: RetrievedContextEntry[];
}

// ---------------------------------------------------------------------------
// Serialisation helpers
// ---------------------------------------------------------------------------

export function toTableRows(apiRows: Record<string, unknown>[]): DatasetRow[] {
  return apiRows.map((r) => {
    const inputs = (r["inputs"] as Record<string, unknown>) ?? {};
    const expectations = (r["expectations"] as Record<string, unknown>) ?? {};

    const question = String(inputs["question"] ?? "");
    const extraInputs: ExtraInput[] = Object.entries(inputs)
      .filter(([k]) => k !== "question")
      .map(([key, value]) => ({ key, value: String(value ?? "") }));

    const expectedResponse = String(expectations["expected_response"] ?? "");

    const rawFacts = expectations["expected_facts"];
    const expectedFacts: string[] = Array.isArray(rawFacts)
      ? rawFacts.map((f) => String(f))
      : [];

    const rawCtx = expectations["expected_retrieved_context"];
    const expectedRetrievedContext: RetrievedContextEntry[] = Array.isArray(rawCtx)
      ? rawCtx.map((c) => {
          if (typeof c === "object" && c !== null) {
            const entry = c as Record<string, unknown>;
            return {
              doc_uri: String(entry["doc_uri"] ?? ""),
              content: String(entry["content"] ?? ""),
            };
          }
          return { doc_uri: "", content: String(c) };
        })
      : [];

    return { question, extraInputs, expectedResponse, expectedFacts, expectedRetrievedContext };
  });
}

export function toApiRows(rows: DatasetRow[]): Record<string, unknown>[] {
  return rows.map((r) => {
    const inputs: Record<string, string> = { question: r.question };
    for (const { key, value } of r.extraInputs) {
      if (key.trim()) inputs[key.trim()] = value;
    }

    const expectations: Record<string, unknown> = {};
    if (r.expectedResponse) expectations["expected_response"] = r.expectedResponse;
    if (r.expectedFacts.length > 0) expectations["expected_facts"] = r.expectedFacts;
    if (r.expectedRetrievedContext.length > 0)
      expectations["expected_retrieved_context"] = r.expectedRetrievedContext;

    return { inputs, expectations };
  });
}

export function emptyRow(): DatasetRow {
  return {
    question: "",
    extraInputs: [],
    expectedResponse: "",
    expectedFacts: [],
    expectedRetrievedContext: [],
  };
}

// ---------------------------------------------------------------------------
// Sub-editors
// ---------------------------------------------------------------------------

interface ExtraInputsEditorProps {
  extraInputs: ExtraInput[];
  onChange: (next: ExtraInput[]) => void;
}

function ExtraInputsEditor({ extraInputs, onChange }: ExtraInputsEditorProps) {
  function updateEntry(index: number, field: keyof ExtraInput, value: string) {
    onChange(extraInputs.map((e, i) => (i === index ? { ...e, [field]: value } : e)));
  }

  function removeEntry(index: number) {
    onChange(extraInputs.filter((_, i) => i !== index));
  }

  function addEntry() {
    onChange([...extraInputs, { key: "", value: "" }]);
  }

  return (
    <div className="space-y-1">
      {extraInputs.map((entry, i) => (
        <div key={i} className="flex gap-1 items-center">
          <input
            type="text"
            placeholder="key"
            value={entry.key}
            onChange={(e) => updateEntry(i, "key", e.target.value)}
            className="w-28 border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-400"
          />
          <span className="text-gray-400 text-xs">:</span>
          <input
            type="text"
            placeholder="value"
            value={entry.value}
            onChange={(e) => updateEntry(i, "value", e.target.value)}
            className="flex-1 border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-400"
          />
          <button
            type="button"
            onClick={() => removeEntry(i)}
            className="text-red-400 hover:text-red-600 text-sm leading-none px-1"
            aria-label="Remove field"
          >
            &times;
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addEntry}
        className="text-xs text-blue-600 hover:underline"
      >
        + Add input field
      </button>
    </div>
  );
}

interface FactsEditorProps {
  facts: string[];
  onChange: (next: string[]) => void;
}

function FactsEditor({ facts, onChange }: FactsEditorProps) {
  function updateFact(index: number, value: string) {
    onChange(facts.map((f, i) => (i === index ? value : f)));
  }

  function removeFact(index: number) {
    onChange(facts.filter((_, i) => i !== index));
  }

  function addFact() {
    onChange([...facts, ""]);
  }

  return (
    <div className="space-y-1">
      {facts.map((fact, i) => (
        <div key={i} className="flex gap-1 items-center">
          <span className="text-gray-400 text-xs w-4 shrink-0">{i + 1}.</span>
          <input
            type="text"
            value={fact}
            onChange={(e) => updateFact(i, e.target.value)}
            placeholder="Expected fact…"
            className="flex-1 border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-400"
          />
          <button
            type="button"
            onClick={() => removeFact(i)}
            className="text-red-400 hover:text-red-600 text-sm leading-none px-1"
            aria-label="Remove fact"
          >
            &times;
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addFact}
        className="text-xs text-blue-600 hover:underline"
      >
        + Add fact
      </button>
    </div>
  );
}

interface SourcesEditorProps {
  sources: RetrievedContextEntry[];
  onChange: (next: RetrievedContextEntry[]) => void;
}

function SourcesEditor({ sources, onChange }: SourcesEditorProps) {
  function updateSource(index: number, field: keyof RetrievedContextEntry, value: string) {
    onChange(sources.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
  }

  function removeSource(index: number) {
    onChange(sources.filter((_, i) => i !== index));
  }

  function addSource() {
    onChange([...sources, { doc_uri: "", content: "" }]);
  }

  return (
    <div className="space-y-2">
      {sources.map((src, i) => (
        <div key={i} className="border border-gray-100 rounded p-2 space-y-1">
          <div className="flex gap-1 items-center justify-between">
            <span className="text-xs text-gray-500">Source {i + 1}</span>
            <button
              type="button"
              onClick={() => removeSource(i)}
              className="text-red-400 hover:text-red-600 text-sm leading-none"
              aria-label="Remove source"
            >
              &times;
            </button>
          </div>
          <input
            type="text"
            placeholder="doc_uri (e.g. s3://bucket/doc.pdf)"
            value={src.doc_uri}
            onChange={(e) => updateSource(i, "doc_uri", e.target.value)}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-400"
          />
          <textarea
            placeholder="Relevant content snippet…"
            value={src.content}
            onChange={(e) => updateSource(i, "content", e.target.value)}
            rows={2}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-400 resize-y"
          />
        </div>
      ))}
      <button
        type="button"
        onClick={addSource}
        className="text-xs text-blue-600 hover:underline"
      >
        + Add source
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary badges for collapsed rows
// ---------------------------------------------------------------------------

function badgeCounts(row: DatasetRow): string[] {
  const badges: string[] = [];
  if (row.extraInputs.length > 0) badges.push(`${row.extraInputs.length} extra input${row.extraInputs.length > 1 ? "s" : ""}`);
  if (row.expectedFacts.length > 0) badges.push(`${row.expectedFacts.length} fact${row.expectedFacts.length > 1 ? "s" : ""}`);
  if (row.expectedRetrievedContext.length > 0) badges.push(`${row.expectedRetrievedContext.length} source${row.expectedRetrievedContext.length > 1 ? "s" : ""}`);
  return badges;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "…";
}

// ---------------------------------------------------------------------------
// Expanded row detail panel
// ---------------------------------------------------------------------------

interface RowDetailProps {
  row: DatasetRow;
  index: number;
  readOnly: boolean;
  onUpdate: (patch: Partial<DatasetRow>) => void;
  onDelete: () => void;
}

function RowDetail({ row, index, readOnly, onUpdate, onDelete }: RowDetailProps) {
  return (
    <div className="border-x border-b border-gray-200 bg-gray-50 px-4 py-4 space-y-4">
      {/* Inputs */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">Inputs</p>
        <div className="space-y-1">
          <label className="text-xs text-gray-500">question *</label>
          {readOnly ? (
            <p className="text-sm whitespace-pre-wrap">{row.question}</p>
          ) : (
            <input
              type="text"
              value={row.question}
              onChange={(e) => onUpdate({ question: e.target.value })}
              className="w-full border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-400 bg-white"
            />
          )}
        </div>
        {readOnly ? (
          row.extraInputs.length > 0 && (
            <div className="space-y-1">
              {row.extraInputs.map((e, j) => (
                <div key={j} className="flex gap-2 text-sm">
                  <span className="text-gray-500 font-mono">{e.key}:</span>
                  <span>{e.value}</span>
                </div>
              ))}
            </div>
          )
        ) : (
          <ExtraInputsEditor
            extraInputs={row.extraInputs}
            onChange={(next) => onUpdate({ extraInputs: next })}
          />
        )}
      </div>

      {/* Expectations */}
      <div className="space-y-3">
        <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">Expectations</p>

        {/* expected_response */}
        <div className="space-y-1">
          <label className="text-xs text-gray-500">expected_response</label>
          {readOnly ? (
            <p className="text-sm whitespace-pre-wrap">{row.expectedResponse}</p>
          ) : (
            <textarea
              value={row.expectedResponse}
              onChange={(e) => onUpdate({ expectedResponse: e.target.value })}
              rows={3}
              className="w-full border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-400 resize-y bg-white"
            />
          )}
        </div>

        {/* expected_facts */}
        <div className="space-y-1">
          <label className="text-xs text-gray-500">expected_facts</label>
          {readOnly ? (
            row.expectedFacts.length > 0 ? (
              <ul className="list-disc list-inside space-y-0.5">
                {row.expectedFacts.map((f, j) => (
                  <li key={j} className="text-sm">{f}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 italic">none</p>
            )
          ) : (
            <FactsEditor
              facts={row.expectedFacts}
              onChange={(next) => onUpdate({ expectedFacts: next })}
            />
          )}
        </div>

        {/* expected_retrieved_context */}
        <div className="space-y-1">
          <label className="text-xs text-gray-500">expected_retrieved_context</label>
          {readOnly ? (
            row.expectedRetrievedContext.length > 0 ? (
              <div className="space-y-2">
                {row.expectedRetrievedContext.map((src, j) => (
                  <div key={j} className="border border-gray-100 rounded p-2 text-xs space-y-1">
                    <p className="font-mono text-blue-700 break-all">{src.doc_uri}</p>
                    <p className="whitespace-pre-wrap text-gray-700">{src.content}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400 italic">none</p>
            )
          ) : (
            <SourcesEditor
              sources={row.expectedRetrievedContext}
              onChange={(next) => onUpdate({ expectedRetrievedContext: next })}
            />
          )}
        </div>
      </div>

      {/* Delete at bottom of expanded panel */}
      {!readOnly && (
        <div className="pt-2 border-t border-gray-200">
          <button
            type="button"
            onClick={onDelete}
            className="text-red-500 hover:text-red-700 text-xs"
          >
            &times; Remove row {index + 1}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main table
// ---------------------------------------------------------------------------

interface Props {
  rows: DatasetRow[];
  onChange: (rows: DatasetRow[]) => void;
  readOnly: boolean;
}

export function DatasetRowsTable({ rows, onChange, readOnly }: Props) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  function toggleExpand(index: number) {
    setExpandedIndex(expandedIndex === index ? null : index);
  }

  function updateRow(index: number, patch: Partial<DatasetRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function deleteRow(index: number) {
    setExpandedIndex(null);
    onChange(rows.filter((_, i) => i !== index));
  }

  function addRow() {
    const nextIndex = rows.length;
    onChange([...rows, emptyRow()]);
    setExpandedIndex(nextIndex);
  }

  if (rows.length === 0) {
    return (
      <div className="text-sm text-gray-500 py-4">
        {readOnly ? (
          "No rows."
        ) : (
          <div className="flex flex-col items-start gap-3">
            <span>No rows yet.</span>
            <button
              type="button"
              onClick={addRow}
              className="border border-gray-300 text-gray-700 px-4 py-1.5 rounded text-sm hover:bg-gray-50"
            >
              + Add row
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-600">
              <th className="py-2 pr-3 w-10">#</th>
              <th className="py-2 pr-3">Question</th>
              <th className="py-2 pr-3 w-1/3">Expected Response</th>
              <th className="py-2 pr-3 w-24">Details</th>
              <th className="py-2 w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isExpanded = expandedIndex === i;
              const badges = badgeCounts(row);
              return (
                <tr key={i} className="group" style={{ verticalAlign: "top" }}>
                  <td colSpan={5} className="p-0">
                    {/* Collapsed summary row */}
                    <div
                      className={`flex items-center cursor-pointer hover:bg-gray-50 px-0 py-2 border-b ${isExpanded ? "border-gray-300 bg-gray-50" : "border-gray-100"}`}
                      onClick={() => toggleExpand(i)}
                    >
                      {/* # */}
                      <span className="w-10 shrink-0 text-gray-400 text-xs pr-3">{i + 1}</span>
                      {/* Question */}
                      <span className="flex-1 pr-3 truncate" title={row.question}>
                        {truncate(row.question || "(empty)", 80)}
                      </span>
                      {/* Expected Response */}
                      <span className="w-1/3 shrink-0 pr-3 text-gray-600 truncate" title={row.expectedResponse}>
                        {truncate(row.expectedResponse || "—", 60)}
                      </span>
                      {/* Badges */}
                      <span className="w-24 shrink-0 pr-3 flex gap-1 flex-wrap">
                        {badges.map((b) => (
                          <span key={b} className="inline-block bg-blue-50 text-blue-600 text-[10px] px-1.5 py-0.5 rounded">
                            {b}
                          </span>
                        ))}
                      </span>
                      {/* Expand chevron */}
                      <span className="w-8 shrink-0 text-center text-gray-400 text-xs">
                        {isExpanded ? "▾" : "▸"}
                      </span>
                    </div>

                    {/* Expanded detail panel */}
                    {isExpanded && (
                      <RowDetail
                        row={row}
                        index={i}
                        readOnly={readOnly}
                        onUpdate={(patch) => updateRow(i, patch)}
                        onDelete={() => deleteRow(i)}
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!readOnly && (
        <button
          type="button"
          onClick={addRow}
          className="mt-3 border border-gray-300 text-gray-700 px-4 py-1.5 rounded text-sm hover:bg-gray-50"
        >
          + Add row
        </button>
      )}
    </div>
  );
}
