class SeatRefused(ValueError):
    """A saved agent the caller may not use, phrased for the person who pressed. A
    ValueError so the HTTP door answers it as a 422 that names the reason."""
