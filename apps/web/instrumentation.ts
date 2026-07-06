export async function register() {
  const appEnv = process.env.NEXT_PUBLIC_APP_ENV ?? "local";
  const fixturesEnabled = process.env.NEXT_PUBLIC_USE_FIXTURES === "true";

  if ((appEnv === "staging" || appEnv === "production") && fixturesEnabled) {
    throw new Error(
      "NEXT_PUBLIC_USE_FIXTURES=true is not allowed in staging or production deployments."
    );
  }
}
