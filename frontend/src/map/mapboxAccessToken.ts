export function applyMapboxAccessToken(engine: { accessToken: string | null | undefined }, token: string | undefined) {
  engine.accessToken = token ?? "";
}
