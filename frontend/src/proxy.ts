export { auth as proxy } from "@/auth";

export const config = {
  matcher: [
    // Protect all routes except static files, images, and auth API
    "/((?!_next/static|_next/image|favicon.ico|api/auth).*)",
  ],
};
