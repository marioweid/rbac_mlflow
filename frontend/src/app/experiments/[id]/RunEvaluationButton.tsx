"use client";

import { useState } from "react";

import { RunEvaluationModal } from "./RunEvaluationModal";

interface Props {
  experimentId: string;
  teamName: string;
}

export function RunEvaluationButton({ experimentId, teamName }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700"
      >
        Run evaluation
      </button>
      {open && (
        <RunEvaluationModal
          experimentId={experimentId}
          teamName={teamName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
