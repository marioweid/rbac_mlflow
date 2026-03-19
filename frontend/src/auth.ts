import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    groups?: string[];
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
  callbacks: {
    authorized({ auth }) {
      return !!auth;
    },
    async jwt({ token, account }) {
      // On initial sign-in, persist the access token
      if (account) {
        token["accessToken"] = account.access_token;
        token["groups"] = account.id_token
          ? (
              JSON.parse(
                Buffer.from(
                  account.id_token.split(".")[1] ?? "",
                  "base64"
                ).toString()
              ) as Record<string, unknown>
            )["groups"]
          : [];
      }
      return token;
    },
    async session({ session, token }) {
      const accessToken = token["accessToken"] as string | undefined;
      if (accessToken !== undefined) {
        session.accessToken = accessToken;
      }
      session.groups = (token["groups"] as string[] | undefined) ?? [];
      return session;
    },
  },
});
