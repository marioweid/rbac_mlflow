"use client";

import { signOut } from "next-auth/react";

export function SignOutButton() {
  return (
    <button
      onClick={() => signOut()}
      className="text-gray-700 hover:text-red-600 font-medium"
    >
      Sign out
    </button>
  );
}
