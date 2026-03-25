import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    groups?: string[];
    error?: string;
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Keycloak({
      clientId: process.env["KEYCLOAK_CLIENT_ID"] ?? "rbac-frontend",
      clientSecret: process.env["KEYCLOAK_CLIENT_SECRET"] ?? "",
      issuer: process.env["KEYCLOAK_ISSUER"] ?? "",
    }),
  ],
  events: {
    async signOut(message) {
      // End the Keycloak session so the next sign-in prompts for credentials
      if ("token" in message && message.token?.["id_token"]) {
        const issuer = process.env["KEYCLOAK_ISSUER"] ?? "";
        const logoutUrl = `${issuer}/protocol/openid-connect/logout?id_token_hint=${message.token["id_token"]}`;
        await fetch(logoutUrl);
      }
    },
  },
  callbacks: {
    authorized({ auth }) {
      return !!auth;
    },
    async jwt({ token, account }) {
      // Initial sign-in — persist tokens and metadata
      if (account) {
        token["accessToken"] = account.access_token;
        token["refreshToken"] = account.refresh_token;
        token["expiresAt"] = account.expires_at;
        token["id_token"] = account.id_token;
        token["groups"] = account.id_token
          ? (
              JSON.parse(
                Buffer.from(
                  account.id_token.split(".")[1] ?? "",
                  "base64",
                ).toString(),
              ) as Record<string, unknown>
            )["groups"]
          : [];
        return token;
      }

      // Token still valid
      if (Date.now() < (token["expiresAt"] as number) * 1000) {
        return token;
      }

      // Token expired — refresh via Keycloak
      try {
        const issuer = process.env["KEYCLOAK_ISSUER"] ?? "";
        const response = await fetch(
          `${issuer}/protocol/openid-connect/token`,
          {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              client_id: process.env["KEYCLOAK_CLIENT_ID"] ?? "rbac-frontend",
              client_secret: process.env["KEYCLOAK_CLIENT_SECRET"] ?? "",
              grant_type: "refresh_token",
              refresh_token: token["refreshToken"] as string,
            }),
          },
        );
        const refreshed = (await response.json()) as Record<string, unknown>;
        if (!response.ok) throw refreshed;

        token["accessToken"] = refreshed["access_token"];
        token["refreshToken"] =
          (refreshed["refresh_token"] as string | undefined) ??
          token["refreshToken"];
        token["expiresAt"] =
          Math.floor(Date.now() / 1000) + (refreshed["expires_in"] as number);
        token["id_token"] =
          (refreshed["id_token"] as string | undefined) ?? token["id_token"];
        return token;
      } catch {
        token["error"] = "RefreshTokenError";
        return token;
      }
    },
    async session({ session, token }) {
      const accessToken = token["accessToken"] as string | undefined;
      if (accessToken !== undefined) {
        session.accessToken = accessToken;
      }
      session.groups = (token["groups"] as string[] | undefined) ?? [];
      if (token["error"]) session.error = token["error"] as string;
      return session;
    },
  },
});
