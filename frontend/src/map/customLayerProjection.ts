export function customLayerProjectionMatrix(
  input: unknown
): ArrayLike<number> {
  const maplibreInput = input as { modelViewProjectionMatrix?: ArrayLike<number> };
  return maplibreInput.modelViewProjectionMatrix ?? input as ArrayLike<number>;
}
