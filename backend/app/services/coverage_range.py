import math

from app.schemas.radar import CoverageRequest


def radar_equation_max_range(payload: CoverageRequest) -> float | None:
    params = payload.reserved_radar_params
    required = [
        params.frequency_hz,
        params.transmit_power_w,
        params.antenna_gain_db,
        params.receiver_sensitivity_dbm,
        params.target_rcs_m2,
    ]
    if any(value is None for value in required):
        return None
    if (
        params.frequency_hz <= 0
        or params.transmit_power_w <= 0
        or params.target_rcs_m2 <= 0
    ):
        return None

    light_speed = 299_792_458.0
    wavelength = light_speed / params.frequency_hz
    gain = 10 ** (params.antenna_gain_db / 10)
    loss = 10 ** ((params.system_loss_db or 0) / 10)
    threshold_dbm = params.receiver_sensitivity_dbm + (params.noise_figure_db or 0)
    threshold_w = 10 ** ((threshold_dbm - 30) / 10)
    if threshold_w <= 0 or loss <= 0:
        return None

    numerator = params.transmit_power_w * gain * gain * wavelength * wavelength * params.target_rcs_m2
    denominator = ((4 * math.pi) ** 3) * threshold_w * loss
    if numerator <= 0 or denominator <= 0:
        return None
    return (numerator / denominator) ** 0.25


def effective_max_range(payload: CoverageRequest) -> tuple[float, float | None]:
    radar_range = radar_equation_max_range(payload)
    if radar_range is None:
        return payload.coverage.max_range_m, None
    return min(payload.coverage.max_range_m, radar_range), radar_range
