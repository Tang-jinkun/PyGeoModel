export function customLayerProjectionMatrix(
  input: unknown
): ArrayLike<number> {
  const maplibreInput = input as {
    defaultProjectionData?: { mainMatrix?: ArrayLike<number> };
  };
  return maplibreInput.defaultProjectionData?.mainMatrix ?? input as ArrayLike<number>;
}
